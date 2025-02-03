import json
import logging
import os
import uuid

from dataclasses import asdict
from datetime import timedelta
from typing import Optional

import portone_server_sdk as portone

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.request import Request

from payment.models import Pays
from plan.models import Plans
from subscription.models import Subs


logger = logging.getLogger(__name__)
User = get_user_model()

# 포트원 API 클라이언트 초기화
secret_key = os.environ.get("IMP_API_SECRET")
if secret_key is None:
    raise ValueError("IMP_API_SECRET 환경 변수가 설정되지 않았습니다.")

portone_client = portone.PaymentClient(secret=secret_key)


def payment_page(request: HttpRequest) -> HttpResponse:
    return render(request, "payment.html")


@csrf_exempt
def get_item(request: Request) -> JsonResponse:
    """
    상품 정보 조회 API
    - 프론트엔드에서 `/api/item` 요청 시, 구독 정보를 반환
    """
    try:
        subscription = Subs.objects.first()  # 예제에서는 첫 번째 구독을 사용
        if not subscription:
            return JsonResponse({"error": "No subscription found"}, status=404)

        return JsonResponse(
            {
                "id": subscription.id,
                "name": f"구독 {subscription.id}",
                "price": float(
                    subscription.plan.price
                ),  # DecimalField를 float으로 변환
                "currency": "KRW",
            }
        )
    except Exception as e:
        logger.error(f"Error fetching item: {e}")
        return JsonResponse({"error": "Failed to retrieve item"}, status=500)


# 프론트엔드에서 `/api/payment/request/` 요청 시, 포트원 API를 호출하여 결제 요청
@csrf_exempt
@require_POST
def request_payment(request: Request) -> JsonResponse:
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        sub_id = data.get("sub_id")

        if not user_id:
            return JsonResponse({"error": "Missing user_id"}, status=400)
        if not sub_id:
            return JsonResponse({"error": "Missing sub_id"}, status=400)

        # 사용자 UUID 변환
        try:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        except ValueError:
            return JsonResponse({"error": "Invalid UUID format"}, status=400)

        # 사용자 검색 또는 생성
        user, _ = User.objects.get_or_create(
            id=user_uuid,
            defaults={
                "email": f"user{user_uuid}@example.com",
                "name": f"User {user_uuid}",
            },
        )

        # 구독 존재 여부 확인 후 생성
        subscription = get_object_or_404(Subs, id=sub_id)

        payment_id = f"ORDER_{timezone.now().strftime('%Y%m%d%H%M%S')}"

        try:
            response = portone_client.pre_register_payment(
                payment_id=payment_id,
                total_amount=int(subscription.plan.price),
                currency="KRW",
            )
            logger.info(f"포트원 결제 요청 성공: {response}")

            response_data = (
                asdict(response)
                if hasattr(response, "__dataclass_fields__")
                else response.__dict__
            )

            return JsonResponse(
                {
                    "payment_id": response_data.get("paymentId", ""),
                    "amount": response_data.get("totalAmount", 0),
                    "currency": response_data.get("currency", "KRW"),
                    "message": "결제 정보 사전 등록 완료",
                },
                status=200,
            )

        except Exception as e:
            logger.error(f"Payment request failed: {e}")
            return JsonResponse(
                {"error": "Payment request failed", "details": str(e)}, status=500
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)


@csrf_exempt
@require_POST
def complete_payment(request: Request) -> JsonResponse:
    """결제 완료 api"""
    try:
        data = json.loads(request.body)
        logger.info(f"결제 완료 요청 데이터: {data}")

        payment_id = data.get("paymentId")
        if not payment_id:
            logger.error("Missing paymentId")
            return JsonResponse({"error": "Missing paymentId"}, status=400)

        payment = sync_payment(payment_id)
        if payment is None:
            logger.error("결제 동기화 실패 (payment is None)")
            return JsonResponse({"error": "결제 동기화 실패"}, status=400)

        return JsonResponse(
            {"payment_id": str(payment.imp_uid), "status": payment.status}
        )

    except json.JSONDecodeError:
        logger.error("Invalid JSON format")
        return JsonResponse({"error": "Invalid JSON format"}, status=400)


def sync_payment(payment_id: str) -> Optional[Pays]:
    """포트원에서 결제 정보를 가져와 Pays 모델과 동기화"""
    logger.info(f"🔍 [sync_payment] 포트원에서 결제 조회 시작: payment_id={payment_id}")

    try:
        actual_payment = portone_client.get_payment(payment_id=payment_id)
        logger.info(f"[sync_payment] 결제 조회 성공: {actual_payment}")

    except portone.payment.GetPaymentError as e:
        logger.error(f"[sync_payment] 결제 정보 조회 실패: {e}")
        return None

    # 결제 정보가 없으면 로그 추가
    if not actual_payment:
        logger.error("[sync_payment] 결제 정보 없음 (None 반환)")
        return None

    logger.info(f"actual_payment type: {type(actual_payment)}")
    logger.info(f"actual_payment data: {actual_payment.__dict__}")

    if not isinstance(actual_payment, portone.payment.PaidPayment):
        logger.error(f"[sync_payment] 잘못된 결제 객체: {type(actual_payment)}")
        return None

    # custom_data에서 `sub_id` 가져오기
    custom_data = (
        json.loads(actual_payment.custom_data) if actual_payment.custom_data else {}
    )
    logger.info(f"[sync_payment] custom_data: {custom_data}")

    sub_id = custom_data.get("sub_id")
    if not sub_id:
        logger.error("[sync_payment] sub_id 없음 → 결제 동기화 실패")
        return None

    # sub_id를 이용하여 구독 정보 확인
    subscription = Subs.objects.filter(id=sub_id).first()
    if not subscription:
        logger.error(f"[sync_payment] 구독 정보 없음 (sub_id={sub_id})")
        return None

    # 사용자 정보 확인 및 변환
    customer_info = actual_payment.customer
    if not customer_info or not customer_info.id:
        logger.error("[sync_payment] 결제 정보에 customer 정보 없음")
        return None

    customer_id = str(customer_info.id)
    user = None

    # customer_id가 UUID인지 확인 후 변환
    try:
        user_uuid = uuid.UUID(customer_id)
        user = get_object_or_404(User, id=user_uuid)
    except ValueError:
        logger.warning(f"[sync_payment] UUID 변환 실패, Email 기반 조회: {customer_id}")
        email = customer_info.email or f"user_{customer_id}@example.com"

        # 사용자 이메일 기반으로 검색, 없으면 생성
        user, _ = User.objects.get_or_create(
            email=email, defaults={"name": customer_info.name or "Unnamed User"}
        )

    # merchant_uid 처리 (중복 방지)
    merchant_uid = str(actual_payment.merchant_id) or str(uuid.uuid4())
    if Pays.objects.filter(merchant_uid=merchant_uid).exists():
        merchant_uid = str(uuid.uuid4())

    # amount 필드 변환 (PaymentAmount → Decimal)
    try:
        amount = float(actual_payment.amount.total)  # 💡 `float()`로 변환하여 저장
    except AttributeError:
        logger.error(f"[sync_payment] 결제 금액 변환 실패: {actual_payment.amount}")
        return None

    # imp_uid 변환
    imp_uid = str(actual_payment.id)  # 💡 `imp_uid`를 문자열로 변환하여 저장

    # 결제 정보 저장 또는 업데이트
    payment, created = Pays.objects.update_or_create(
        imp_uid=imp_uid,
        defaults={
            "user": user,
            "subs": subscription,
            "merchant_uid": merchant_uid,
            "amount": amount,
            "status": "PAID",
            "paid_at": actual_payment.paid_at or now(),
        },
    )

    # 결제 검증
    if not verify_payment(actual_payment, subscription):
        logger.error("[sync_payment] 결제 검증 실패")
        return None

    # 상태 업데이트
    payment.status = "PAID"
    payment.save()

    logger.info(f"✅ [sync_payment] 결제 성공: {imp_uid} ({payment.amount})")
    return payment


def verify_payment(payment: portone.payment.PaidPayment, subscription: Subs) -> bool:
    """결제 검증 로직"""
    logger.info(
        f"🔍 [verify_payment] 검증 시작 → 결제 ID: {payment.id}, 구독 ID: {subscription.id}"
    )

    # 주문명 비교 (DB에 저장하지 않고 요금제 이름으로 비교)
    expected_order_name = subscription.plan.plan_name  # 구독 요금제 이름
    actual_order_name = (
        payment.order_name if hasattr(payment, "order_name") else expected_order_name
    )

    if actual_order_name != expected_order_name:
        logger.error(
            f"[verify_payment] 주문명이 일치하지 않음: {actual_order_name} ≠ {expected_order_name}"
        )
        return False

    # 결제 금액 비교
    expected_amount = float(subscription.plan.price)  # Decimal → float 변환
    actual_amount = float(payment.amount.total)

    if actual_amount != expected_amount:
        logger.error(
            f"[verify_payment] 결제 금액 불일치: {actual_amount} ≠ {expected_amount}"
        )
        return False

    # 통화 비교
    if payment.currency != "KRW":
        logger.error(f"[verify_payment] 통화 불일치: {payment.currency} ≠ KRW")
        return False

    logger.info(f" [verify_payment] 결제 검증 성공: 결제 ID {payment.id}")
    return True


# @csrf_exempt
# @require_POST
# def receive_webhook(request):
#     """포트원 Webhook 처리"""
#     try:
#         body = request.body.decode("utf-8")
#         headers = request.headers
#
#         webhook = portone.webhook.verify(
#             os.environ.get("V2_WEBHOOK_SECRET"), body, headers
#         )
#
#     except portone.webhook.WebhookVerificationError:
#         return JsonResponse({"error": "Bad Request"}, status=400)
#
#     if isinstance(webhook, dict) and isinstance(webhook.get("data"), portone.webhook.WebhookTransactionData):
#         sync_payment(webhook["data"].payment_id)
#
#     return JsonResponse({"message": "OK"}, status=200)

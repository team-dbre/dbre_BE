import json
import logging
import os
import uuid

from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import portone_server_sdk as portone

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from portone_server_sdk._generated.common.billing_key_payment_input import (
    BillingKeyPaymentInput,
)
from portone_server_sdk._generated.common.customer_input import CustomerInput
from portone_server_sdk._generated.common.customer_name_input import CustomerNameInput
from portone_server_sdk._generated.common.payment_amount_input import PaymentAmountInput
from portone_server_sdk._generated.payment.billing_key.client import BillingKeyClient
from portone_server_sdk._generated.payment.client import PaymentClient
from portone_server_sdk._generated.payment.payment_schedule.create_payment_schedule_response import (
    CreatePaymentScheduleResponse,
)
from rest_framework.request import Request

from payment.models import BillingKey, Pays
from plan.models import Plans
from subscription.models import SubHistories, Subs
from user.models import CustomUser


logger = logging.getLogger(__name__)
User = get_user_model()

# 포트원 API 클라이언트 초기화
secret_key = os.environ.get("IMP_API_SECRET")
if secret_key is None:
    raise ValueError("IMP_API_SECRET 환경 변수가 설정되지 않았습니다.")

portone_client = portone.PaymentClient(secret=secret_key)
PORTONE_API_URL = "https://api.portone.io/v2"
IMP_API_KEY = os.getenv("STORE_ID")
PORTONE_CHANNEL_KEY = os.getenv("PORTONE_CHANNEL_KEY")
portone_client2 = PaymentClient(secret=secret_key or "")
billing_key_client = BillingKeyClient(secret=secret_key or "")


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


@csrf_exempt
@require_POST
def cancel_payment(request: Request) -> HttpResponse:
    """환불 API"""
    try:
        data = json.loads(request.body)
        imp_uid = data.get("imp_uid")
        reason = data.get("reason", "고객 요청 환불")

        if not imp_uid:
            return JsonResponse({"error": "Missing imp_uid"}, status=400)

        # 결제 정보 가져오기
        pays = Pays.objects.filter(imp_uid=imp_uid).first()
        if not pays:
            return JsonResponse({"error": "결제 내역을 찾을 수 없습니다."}, status=404)

        # 환불 가능 여부 확인
        if pays.status in ["CANCELLED", "REFUNDED"]:
            return JsonResponse({"error": "이미 취소된 결제입니다."}, status=400)

        # 구독 정보 가져오기
        subscription = Subs.objects.filter(id=pays.subs.id).first()
        if not subscription:
            return JsonResponse({"error": "구독 정보를 찾을 수 없습니다."}, status=404)

        start_date = subscription.start_date
        end_date = subscription.end_date or (
            start_date + timedelta(days=30)
        )  # 예외 처리
        today = now().date()

        # 사용 여부 확인 (예: 서비스 사용 기록이 없으면 전액 환불)
        service_used = False  # 🚨 실제 서비스 사용 여부 체크하는 로직 필요

        # 전액 환불 (서비스 미사용)
        if not service_used:
            refund_amount = pays.amount  # 100% 환불

        # 남은 기간 계산 (서비스 사용)
        else:
            total_days = (end_date - start_date).days  # 한 달 기준 총 일 수
            used_days = (today - start_date.date()).days  # 사용한 일 수
            remaining_days = total_days - used_days  # 남은 일 수

            if remaining_days <= 0:
                return JsonResponse(
                    {"error": "구독이 이미 만료되어 환불이 불가합니다."}, status=400
                )

            refund_amount = (
                Decimal(remaining_days) / Decimal(total_days)
            ) * pays.amount
            refund_amount = Decimal(refund_amount).quantize(
                Decimal("0.01")
            )  # 소수점 반올림

        logger.info(f"[cancel_payment] 환불 금액 계산 완료: {refund_amount}")

        # 포트원 환불 요청
        try:
            refund_response = portone_client.cancel_payment(
                payment_id=imp_uid,
                amount=int(refund_amount),
                reason=reason,
            )
            logger.info(
                f"✅ [cancel_payment] 환불 성공 응답: {refund_response.__dict__}"
            )

        except portone.payment.CancelPaymentError as e:
            logger.error(f"[cancel_payment] 환불 실패: {e}")
            return JsonResponse({"error": "환불 실패", "details": str(e)}, status=500)

        # 결제 상태 업데이트
        pays.status = "REFUNDED"
        pays.save()

        return JsonResponse(
            {
                "imp_uid": pays.imp_uid,
                "status": pays.status,
                "refund_amount": refund_amount,
                "message": "환불 성공",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)


def subscription_payment_page(request: HttpRequest) -> HttpResponse:
    """정기 결제 페이지"""
    return render(request, "subscription_payment.html")


@csrf_exempt
def store_billing_key(request: HttpRequest) -> HttpResponse:
    """Billing Key 저장 API (포트원 SDK 응답값 저장)"""
    try:
        data = json.loads(request.body)
        user_id = data.get("user_id")
        billing_key = data.get("billing_key")

        if not user_id or not billing_key:
            return JsonResponse({"error": "Missing user_id or billing_key"}, status=400)

        user = get_object_or_404(CustomUser, id=user_id)

        # Billing Key 저장
        BillingKey.objects.update_or_create(
            user=user, defaults={"billing_key": billing_key}
        )

        logger.info(f"Billing Key 저장 성공: {billing_key} (User: {user_id})")
        return JsonResponse({"message": "Billing Key 저장 성공"}, status=200)

    except Exception as e:
        logger.error(f"Billing Key 저장 실패: {e}")
        return JsonResponse(
            {"error": "Billing Key 저장 실패", "details": str(e)}, status=500
        )


@csrf_exempt
def request_subscription_payment(request: Request) -> JsonResponse:
    """포트원 SDK를 사용한 정기 결제 API"""
    logger.info("[request_subscription_payment] 정기 결제 요청 수신")

    try:
        if not request.body:
            logger.error("요청 본문이 비어 있음")
            return JsonResponse({"error": "Empty request body"}, status=400)

        logger.info(f"요청 본문: {request.body.decode('utf-8')}")

        data = json.loads(request.body.decode("utf-8"))

        # 필수 필드 검증
        required_fields = ["user_id", "plan_id", "payment_id", "billing_key"]
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return JsonResponse(
                {"error": "Missing required fields", "missing_fields": missing_fields},
                status=400,
            )

        # UUID 형식 검증
        try:
            user_uuid = uuid.UUID(data["user_id"])
        except ValueError:
            return JsonResponse({"error": "Invalid user_id format"}, status=400)

        billing_key = data["billing_key"].strip()

        # 데이터 조회
        try:
            user = CustomUser.objects.get(id=user_uuid)
            plan = Plans.objects.get(id=data["plan_id"])
            billing_key_obj = BillingKey.objects.get(user=user)
            if billing_key_obj.billing_key != billing_key:
                logger.error(
                    f"Billing Key 불일치: {billing_key_obj.billing_key} != {billing_key}"
                )
                return JsonResponse({"error": "Billing Key 불일치"}, status=400)
            logger.info(f"Billing Key 조회 성공: {billing_key}")
        except (
            CustomUser.DoesNotExist,
            Plans.DoesNotExist,
            BillingKey.DoesNotExist,
        ) as e:
            return JsonResponse({"error": str(e)}, status=404)

        # ✅ 기존 구독 확인 후 가져오기 (중복 방지)
        existing_sub = Subs.objects.filter(user=user, plan=plan).first()
        if existing_sub:
            logger.info(f"기존 구독 정보 존재: {existing_sub.id}")
            sub = existing_sub
        else:
            # 새로운 구독 생성
            next_billing_date = now() + relativedelta(months=1)
            sub = Subs.objects.create(
                user=user,
                plan=plan,
                billing_key=billing_key_obj,
                next_bill_date=next_billing_date,
                auto_renew=True,
            )
            logger.info(f"새로운 구독 생성: {sub.id}")

        # `payment_id` 32자 이하로 제한
        short_payment_id = f"PAY{uuid.uuid4().hex[:18]}"
        logger.info(f"생성된 결제 요청 ID: {short_payment_id}")

        # CustomerInput 객체 생성
        customer_info = CustomerInput(
            id=str(user.id),
            email=user.email or "",
            name=CustomerNameInput(full=user.name or "Unnamed User"),
        )

        # 포트원 결제 요청
        logger.info(
            f"[포트원 결제 요청] payment_id: {short_payment_id}, order_name: {plan.plan_name}, amount: {plan.price}, currency: KRW"
        )

        try:
            response = portone_client2.pay_with_billing_key(
                payment_id=short_payment_id,
                billing_key=billing_key.strip(),
                order_name=plan.plan_name,
                amount=PaymentAmountInput(total=int(plan.price)),
                currency="KRW",
                customer=customer_info,
                bypass={"pgProvider": "kpn"},
            )

            logger.info(
                f"[request_subscription_payment] 포트원 결제 요청 성공: {response}"
            )

        except Exception as e:
            logger.error(f"🚨 포트원 결제 요청 실패: {e}")
            return JsonResponse(
                {"error": "PortOne payment request failed", "details": str(e)},
                status=500,
            )
        # 다음 결제일 설정
        next_billing_date = now() + relativedelta(months=1)
        sub.next_bill_date = next_billing_date
        sub.save(update_fields=["next_bill_date"])
        logger.info(f"다음 결제일: {sub.next_bill_date}")

        # 포트원 응답에서 결제 성공 여부 확인
        try:
            if not response.payment or not response.payment.pg_tx_id:
                logger.warning(
                    f"[request_subscription_payment] 결제 취소됨 또는 실패: {response}"
                )
                return JsonResponse(
                    {"error": "Payment was canceled or failed"}, status=400
                )

            payment_id_response = response.payment.pg_tx_id
            logger.info(f"결제 완료 - Payment ID: {payment_id_response}")

        except Exception as e:
            logger.error(f"[request_subscription_payment] 응답 처리 실패: {e}")
            return JsonResponse(
                {"error": "Failed to process payment response"}, status=500
            )

        # 결제 정보 저장
        try:
            payment = Pays.objects.create(
                user=user,
                subs=sub,
                imp_uid=payment_id_response,  # 포트원에서 받은 실제 결제 ID 저장
                merchant_uid=short_payment_id,  # 내부적으로 사용하는 결제 ID
                amount=plan.price,
                status="PAID",
            )
            logger.info(f"결제 정보 저장 완료: {payment.id}")

            # 사용자 구독 상태 변경
            user.sub_status = "active"
            user.save(update_fields=["sub_status"])
            logger.info(f"📌 사용자 {user.id}의 구독 상태를 'active'로 업데이트")

            # 구독 변경 기록 추가
            SubHistories.objects.create(
                sub=sub,
                user=user,
                plan=plan,
                change_date=timezone.now(),
                status="renewal",
            )

        except Exception as e:
            logger.error(f"결제 정보 저장 실패: {str(e)}")
            return JsonResponse(
                {"error": "Failed to save payment information", "details": str(e)},
                status=500,
            )

        # 다음달 결제 예약 추가
        next_billing_date = now() + relativedelta(months=1)
        scheduled_payment_id = f"SUBS{uuid.uuid4().hex[:18]}"

        try:
            schedule_response: CreatePaymentScheduleResponse = (
                portone_client2.payment_schedule.create_payment_schedule(
                    payment_id=scheduled_payment_id,
                    payment=BillingKeyPaymentInput(
                        billing_key=billing_key.strip(),
                        order_name=plan.plan_name,
                        amount=PaymentAmountInput(total=int(plan.price)),
                        currency="KRW",
                        customer=customer_info,
                    ),
                    time_to_pay=next_billing_date.isoformat(),
                )
            )

            logger.info(
                f"[request_subscription_payment] 다음 결제 예약 성공 - Payment ID: {scheduled_payment_id}, Response: {schedule_response}"
            )

            # 예약 성공 시 다음 결제일 저장
            sub.next_bill_date = next_billing_date
            sub.save(update_fields=["next_bill_date"])

        except Exception as e:
            logger.error(f"예약 결제 실패: {e}")
            return JsonResponse(
                {"error": "Failed to schedule next payment", "details": str(e)},
                status=500,
            )

        return JsonResponse(
            {
                "message": "정기 결제 및 다음 결제 예약 성공",
                "payment_id": payment_id_response,
                "next_payment_id": scheduled_payment_id,
                "next_billing_date": next_billing_date.isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"[request_subscription_payment] 예외 발생: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def portone_webhook(request: HttpRequest) -> HttpResponse:
    """포트원 결제 웹훅(Webhook) 엔드포인트"""
    try:
        body = json.loads(request.body.decode("utf-8"))
        logger.info(f"📌 [Webhook] 수신 데이터: {body}")

        imp_uid = body.get("imp_uid")
        status = body.get("status")
        merchant_uid = body.get("merchant_uid")

        if not imp_uid or not status or not merchant_uid:
            return JsonResponse({"error": "Missing required fields"}, status=400)

        # 결제 정보 조회
        payment = Pays.objects.filter(merchant_uid=merchant_uid).first()
        if not payment:
            return JsonResponse({"error": "Payment not found"}, status=404)

        # 결제 성공 시 - 구독 갱신
        if status == "paid":
            subscription = Subs.objects.filter(user=payment.user).first()

            if subscription:
                # 기존 결제일이 None이면 현재 날짜 사용
                current_bill_date = subscription.next_bill_date or now()
                next_bill_date = current_bill_date + relativedelta(months=1)

                subscription.next_bill_date = next_bill_date
                subscription.auto_renew = True
                subscription.save()

                logger.info(
                    f"✅ [Webhook] 결제 성공, 다음 결제일: {subscription.next_bill_date}"
                )

        # 결제 실패 시 - 자동 갱신 해제 및 관리자 알림
        elif status in ["failed", "cancelled"]:
            payment.status = "FAILED"
            payment.save()

            subscription = Subs.objects.filter(user=payment.user).first()
            if subscription:
                subscription.auto_renew = False
                subscription.save()

            logger.error(f"❌ [Webhook] 결제 실패 - auto_renew 비활성화")

        return JsonResponse({"message": "Webhook processed successfully"})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
    except Exception as e:
        logger.error(f"[Webhook] 예외 발생: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST  # POST 요청만 허용
def receive_webhook(request: Request) -> JsonResponse:
    """포트원 결제 웹훅(Webhook) 처리"""
    try:
        # 요청 방식 확인
        if request.method != "POST":
            logger.error("❌ [WebHook] 잘못된 요청 방식: GET 요청 수신")
            return JsonResponse({"error": "Only POST method allowed"}, status=405)

        # 요청 본문 확인
        if not request.body:
            logger.error("❌ [WebHook] 요청 본문 없음")
            return JsonResponse({"error": "Empty request body"}, status=400)

        # JSON 데이터 파싱
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"❌ [WebHook] JSON 파싱 실패: {str(e)}")
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        logger.info(
            f"📌 [WebHook] 포트원 웹훅 수신: {json.dumps(data, indent=4, ensure_ascii=False)}"
        )

        # 필수 필드 확인
        payment_id = data.get("paymentId")
        status = data.get("status")  # 'paid', 'failed', 'cancelled' 등

        if not payment_id:
            logger.error("❌ [WebHook] paymentId 없음")
            return JsonResponse({"error": "Missing paymentId"}, status=400)

        # 결제 정보 업데이트
        payment = Pays.objects.filter(imp_uid=payment_id).first()
        if payment:
            payment.status = status.upper()
            payment.save()
            logger.info(
                f"✅ [WebHook] 결제 상태 업데이트: {payment_id} → {status.upper()}"
            )
        else:
            logger.warning(f"⚠️ [WebHook] 결제 정보 없음: {payment_id}")

        return JsonResponse({"message": "Webhook received successfully"}, status=200)

    except Exception as e:
        logger.error(f"❌ [WebHook] 처리 실패: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def get_billing_key(request: Request, user_id: str) -> HttpResponse:
    """특정 사용자의 Billing Key 조회 API"""
    try:
        # 로깅 추가
        logger.info(f"[get_billing_key] Billing Key 조회 요청 - User ID: {user_id}")

        # UUID 형식 검증
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            logger.error(f"[get_billing_key] 잘못된 UUID 형식 - User ID: {user_id}")
            return JsonResponse({"error": "잘못된 사용자 ID 형식입니다."}, status=400)

        # 사용자 조회
        user = get_object_or_404(CustomUser, id=user_uuid)

        try:
            # Billing Key 조회
            billing_key = BillingKey.objects.get(user=user)
            logger.info(f"[get_billing_key] Billing Key 조회 성공 - User ID: {user_id}")

            return JsonResponse(
                {
                    "message": "Billing Key 조회 성공",
                    "billing_key": billing_key.billing_key,
                    "created_at": billing_key.created_at.isoformat(),
                }
            )

        except BillingKey.DoesNotExist:
            logger.warning(f"[get_billing_key] Billing Key 없음 - User ID: {user_id}")
            return JsonResponse({"error": "등록된 Billing Key가 없습니다."}, status=404)

    except CustomUser.DoesNotExist:
        logger.error(f"[get_billing_key] 사용자 없음 - User ID: {user_id}")
        return JsonResponse({"error": "사용자를 찾을 수 없습니다."}, status=404)

    except Exception as e:
        logger.error(
            f"[get_billing_key] 예외 발생 - User ID: {user_id}, Error: {str(e)}"
        )
        return JsonResponse(
            {"error": "Billing Key 조회 중 오류가 발생했습니다.", "details": str(e)},
            status=500,
        )

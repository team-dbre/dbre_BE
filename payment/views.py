import json
import logging

from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from payment.models import BillingKey
from payment.services.web_hook_service import verify_signature
from subscription.models import Subs

from .serializers import (
    BillingKeySerializer,
    PauseSubscriptionSerializer,
    RefundResponseSerializer,
    RefundSerializer,
    ResumeSubscriptionSerializer,
    SubscriptionPaymentSerializer,
)
from .services.payment_service import (
    RefundService,
    SubscriptionPaymentService,
    SubscriptionService,
)
from .utils import (
    cancel_scheduled_payments,
    check_billing_key_status,
    delete_billing_key_with_retry,
    fetch_scheduled_payments,
    schedule_new_payment,
    update_billing_key_info,
)


logger = logging.getLogger(__name__)
User = get_user_model()


def subscription_payment_page(request: HttpRequest) -> HttpResponse:
    """정기 결제 페이지"""
    return render(request, "subscription_payment.html")


@extend_schema(tags=["payment"])
class StoreBillingKeyView(APIView):
    """포트원 Billing Key 저장 API"""

    permission_classes = [IsAuthenticated]

    serializer_class = BillingKeySerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Billing Key 저장 로직"""
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                billing_key = serializer.save()
                logger.info(
                    f"[StoreBillingKey] Billing Key 저장 성공: {billing_key.billing_key}"
                )

            update_billing_key_info(billing_key, billing_key.billing_key)

            return Response(
                {
                    "message": "Billing Key 저장 성공",
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"[StoreBillingKey] Billing Key 저장 실패: {str(e)}")
            return Response(
                {"error": "Billing Key 저장 실패", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:

        user = request.user
        billing_key_obj = BillingKey.objects.filter(user=user).first()
        if not billing_key_obj:
            logger.warning(f"Billing Key 없음 - User ID: {user.id}")
            return Response(
                {"error": "삭제할 Billing Key가 존재하지 않습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        billing_key = billing_key_obj.billing_key

        reason = "사용자 요청으로 인한 삭제"

        response = delete_billing_key_with_retry(billing_key, reason)
        if not response:
            logger.error(f" DeleteBillingKey 빌링키 삭제 실패 - User ID: {user.id}")
            return Response(
                {"error": "Billing Key 삭제 실패"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        billing_key_obj.delete()
        logger.info(f"빌링키 삭제 성공 {user.id}")

        return Response({"message": "빌링키 삭제 성공"}, status=status.HTTP_200_OK)

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:

        # 사용자 조회
        user = request.user
        logger.info(f"[get_billing_key] Billing Key 조회 요청 - User ID: {user.id}")

        # Billing Key 조회
        billing_key = BillingKey.objects.filter(user=user).first()
        if not billing_key:
            logger.warning(f"[get_billing_key] Billing Key 없음 - User ID: {user.id}")
            return Response(
                {"error": "등록된 Billing Key가 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(f"[get_billing_key] Billing Key 조회 성공 - User ID: {user.id}")

        serializer = self.serializer_class(billing_key)
        return Response(serializer.data, status=status.HTTP_200_OK)


def subscription_service(request: HttpRequest) -> HttpResponse:
    return render(request, "update.html")


@extend_schema(tags=["payment"])
class UpdateBillingKeyView(APIView):
    """Billing Key 변경 API"""

    permission_classes = [IsAuthenticated]
    serializer_class = BillingKeySerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_billing_key = request.data.get("billing_key")
        plan_id = request.data.get("plan_id")
        amount = request.data.get("amount")

        try:
            user = request.user

            # 기존 Billing Key 가져오기
            try:
                billing_key_obj = BillingKey.objects.get(user=user)
                old_billing_key = billing_key_obj.billing_key
                logger.info(f" 기존 Billing Key: {old_billing_key}")
            except BillingKey.DoesNotExist:
                logger.warning(f"기존 Billing Key가 존재하지 않음: user_id={user.id}")
                return Response(
                    {"error": "기존 Billing Key가 존재하지 않습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # 기존 예약된 결제 조회
            scheduled_payments = fetch_scheduled_payments(old_billing_key, plan_id)
            logger.info(f"조회된 예약 결제 리스트: {scheduled_payments}")

            # 기존 예약된 결제가 없는 경우 빌링키만 업데이트
            if not scheduled_payments:
                logger.info(f"기존 빌링키에 예약된 결제가 없음 빌링키만 업데이트")
                billing_key_obj.billing_key = new_billing_key
                billing_key_obj.save()

                serializer = BillingKeySerializer(billing_key_obj)
                return Response(serializer.data, status=status.HTTP_200_OK)

            # 예약된 결제 취소
            cancel_scheduled_payments(old_billing_key, plan_id)

            # 새로운 Billing Key로 기존 결제일 유지하면서 재등록
            response = schedule_new_payment(
                user, old_billing_key, new_billing_key, plan_id, amount
            )
            if not response:
                raise ValueError(
                    "새로운 Billing Key로 예약 결제를 등록하는 데 실패했습니다."
                )

            billing_key_response = delete_billing_key_with_retry(
                old_billing_key, plan_id
            )
            if not billing_key_response:
                raise ValueError("포트원 빌링키 삭제를 실패했습니다")

            # Billing Key 정보 업데이트 (예약 정보 변경 후 저장)
            update_billing_key_info(billing_key_obj, new_billing_key)

            serializer = BillingKeySerializer(billing_key_obj)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Billing Key 변경 실패: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=["payment"])
class RequestSubscriptionPaymentView(APIView):
    """포트원 SDK를 사용한 정기 결제 API"""

    permission_classes = [IsAuthenticated]

    serializer_class = SubscriptionPaymentSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        logger.info("[request_subscription_payment] 정기 결제 요청 수신")

        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        service = SubscriptionPaymentService(
            user=validated_data["user"],
            plan=validated_data["plan"],
            billing_key=validated_data["billing_key"],
        )

        try:
            with transaction.atomic():
                sub = service.create_subscription()
                short_payment_id, billing_key_payment_summary = service.process_payment(
                    sub
                )
                payment = service.save_payment(
                    sub, short_payment_id, billing_key_payment_summary
                )
                scheduled_payment_id = service.schedule_next_payment(sub)

            return Response(
                {
                    "message": "정기 결제 및 다음 결제 예약 성공",
                    "next_billing_date": (
                        sub.next_bill_date.isoformat() if sub.next_bill_date else None
                    ),
                },
                status=status.HTTP_201_CREATED,
            )

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[request_subscription_payment] 예외 발생: {e}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# @extend_schema(tags=["payment"])
# @method_decorator(csrf_exempt, name="dispatch")
# class PortOneWebhookView(APIView):
#
#     def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
#         try:
#             body = request.body.decode("utf-8")
#             data = json.loads(body)
#             signature = request.headers.get("x-portone-signature")
#
#             if not verify_signature(request, signature):
#                 logger.error("Webhook signature verification failed")
#                 return Response(
#                     {"message": "Signature verification failed"},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#
#             payment_id = data.get("paymentId")
#             status_received = data.get("status")
#             amount_received = data.get("amount")
#
#             if not payment_id:
#                 logger.error("Missing paymentId in webhook data")
#                 return Response(
#                     {"message": "Bad Request - Missing paymentId"},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#
#             try:
#                 pay_record = Pays.objects.get(imp_uid=payment_id)
#             except Pays.DoesNotExist:
#                 logger.error(f"Payment with imp_uid {payment_id} not found")
#                 return Response(
#                     {"message": "Payment not found"}, status=status.HTTP_404_NOT_FOUND
#                 )
#
#             if pay_record.amount != amount_received:
#                 logger.warning(
#                     f"Payment amount mismatch: Expected {pay_record.amount}, Received {amount_received}"
#                 )
#                 return Response(
#                     {"message": "Amount mismatch"}, status=status.HTTP_400_BAD_REQUEST
#                 )
#
#             # 결제 상태 업데이트
#             pay_record.status = status_received.upper()
#             pay_record.save()
#             logger.info(f"Payment {payment_id} updated successfully.")
#
#             return Response(
#                 {"message": "Webhook processed successfully"}, status=status.HTTP_200_OK
#             )
#
#         except json.JSONDecodeError:
#             logger.error("Invalid JSON received in webhook")
#             return Response(
#                 {"message": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST
#             )
#         except Exception as e:
#             logger.exception(f"Unexpected error in webhook: {e}")
#             return Response(
#                 {"message": "Internal Server Error"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             )


@extend_schema(tags=["payment"])
@method_decorator(csrf_exempt, name="dispatch")
class PortOneWebhookView(APIView):

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            body = request.body.decode("utf-8")
            data = json.loads(body)
            signature = request.headers.get("x-portone-signature")

            if not signature or not verify_signature(request):
                logger.error("Webhook signature verification failed")
                return Response(
                    {"message": "Signature verification failed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 빌링키 발급 Webhook 처리
            billing_key = data.get("billingKey")
            card_company = data.get("card", {}).get("cardCompany")
            card_number_masked = data.get("card", {}).get("cardNumberMasked")

            if billing_key:
                logger.info(f"Billing Key issued for customer {billing_key}")
                logger.info(f"Card Info: {card_company} - {card_number_masked}")

                #  DB에 카드 정보 및 빌링키 저장
                BillingKey.objects.create(
                    billing_key=billing_key,
                    card_name=card_company,
                    card_number=card_number_masked,
                )

                return Response(
                    {"message": "Billing Key processed successfully"},
                    status=status.HTTP_200_OK,
                )

            return Response(
                {"message": "No billing key found"}, status=status.HTTP_400_BAD_REQUEST
            )

        except json.JSONDecodeError:
            logger.error("Invalid JSON received in webhook")
            return Response(
                {"message": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.exception(f"Unexpected error in webhook: {e}")
            return Response(
                {"message": "Internal Server Error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(tags=["payment"])
class RefundSubscriptionView(APIView):
    """포트원 API를 이용한 결제 취소 및 환불 API"""

    permission_classes = [IsAuthenticated]

    serializer_class = RefundSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """환불 요청 처리"""
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        user = request.user
        subscription = validated_data["subscription"]
        cancelled_reason = validated_data.get("cancelled_reason", "")
        other_reason = validated_data.get("other_reason", "")

        try:
            with transaction.atomic():
                # 환불 서비스 실행
                service = RefundService(
                    user, subscription, cancelled_reason, other_reason
                )
                refund_response = service.process_refund()

                # 응답 시리얼라이저 적용
                response_serializer = RefundResponseSerializer(refund_response)
                if "error" in refund_response:
                    return Response(
                        response_serializer.data, status=status.HTTP_400_BAD_REQUEST
                    )

                return Response(response_serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"환불 처리 중 오류 발생: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["payment"])
class PauseSubscriptionView(APIView):
    """구독 중지 API"""

    permission_classes = [IsAuthenticated]
    serializer_class = PauseSubscriptionSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        plan_id = request.data.get("plan_id")

        if not plan_id:
            return Response("error", status=status.HTTP_400_BAD_REQUEST)

        try:
            subscription = Subs.objects.get(user=user, plan_id=plan_id)
        except Subs.DoesNotExist:
            return Response(
                {"error": "해당 유저의 구독 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        service = SubscriptionService(subscription)
        result = service.pause_subscription()

        return Response(
            result,
            status=(
                status.HTTP_200_OK
                if "message" in result
                else status.HTTP_400_BAD_REQUEST
            ),
        )


@extend_schema(tags=["payment"])
class ResumeSubscriptionView(APIView):
    """구독 재개 API"""

    permission_classes = [IsAuthenticated]
    serializer_class = ResumeSubscriptionSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response("error", status=status.HTTP_400_BAD_REQUEST)

        try:
            subscription = Subs.objects.get(user=user, plan_id=plan_id)
        except Subs.DoesNotExist:
            return Response(
                {"error": "해당 유저의 구독 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        service = SubscriptionService(subscription)
        result = service.resume_subscription()

        return Response(
            result,
            status=(
                status.HTTP_200_OK
                if "message" in result
                else status.HTTP_400_BAD_REQUEST
            ),
        )

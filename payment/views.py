import json
import logging
import uuid

from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from payment.models import BillingKey
from payment.services.web_hook_service import WebhookService
from user.models import CustomUser

from .serializers import (
    BillingKeySerializer,
    GetBillingKeySerializer,
    RefundResponseSerializer,
    RefundSerializer,
    SubscriptionPaymentSerializer,
    WebhookSerializer,
)
from .services.payment_service import RefundService, SubscriptionPaymentService


logger = logging.getLogger(__name__)
User = get_user_model()


def subscription_payment_page(request: HttpRequest) -> HttpResponse:
    """정기 결제 페이지"""
    return render(request, "subscription_payment.html")


class StoreBillingKeyView(APIView):
    """포트원 Billing Key 저장 API"""

    serializer_class = BillingKeySerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Billing Key 저장 로직"""
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                billing_key = serializer.save()
                logger.info(
                    f"[StoreBillingKey] Billing Key 저장 성공: {billing_key.billing_key}"
                )

            return Response(
                {
                    "message": "Billing Key 저장 성공",
                    "billing_key": billing_key.billing_key,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"[StoreBillingKey] Billing Key 저장 실패: {str(e)}")
            return Response(
                {"error": "Billing Key 저장 실패", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RequestSubscriptionPaymentView(APIView):
    """포트원 SDK를 사용한 정기 결제 API"""

    serializer_class = SubscriptionPaymentSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        logger.info("[request_subscription_payment] 정기 결제 요청 수신")

        serializer = self.serializer_class(data=request.data)
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
                    "payment_id": payment.imp_uid,
                    "next_payment_id": scheduled_payment_id,
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


class GetBillingKeyView(APIView):
    """특정 사용자의 Billing Key 조회 API"""

    serializer_class = GetBillingKeySerializer

    def get(
        self, request: Request, user_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        logger.info(f"[get_billing_key] Billing Key 조회 요청 - User ID: {user_id}")

        # UUID 형식 검증
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            logger.error(f"[get_billing_key] 잘못된 UUID 형식 - User ID: {user_id}")
            return Response(
                {"error": "잘못된 사용자 ID 형식입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 사용자 조회
        user = get_object_or_404(CustomUser, id=user_uuid)

        # Billing Key 조회
        billing_key = BillingKey.objects.filter(user=user).first()
        if not billing_key:
            logger.warning(f"[get_billing_key] Billing Key 없음 - User ID: {user_id}")
            return Response(
                {"error": "등록된 Billing Key가 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(f"[get_billing_key] Billing Key 조회 성공 - User ID: {user_id}")

        serializer = self.serializer_class(billing_key)
        return Response(serializer.data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class PortOneWebhookView(APIView):
    """포트원 결제 웹훅(Webhook) API"""

    serializer_class = WebhookSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            # JSON 데이터 파싱 및 검증
            data = json.loads(request.body.decode("utf-8"))
            serializer = self.serializer_class(data=data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            service = WebhookService(**validated_data)
            response_data = service.process_webhook()

            return Response(response_data, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid JSON format"}, status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[Webhook] 예외 발생: {e}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RefundSubscriptionView(APIView):
    """포트원 API를 이용한 결제 취소 및 환불 API"""

    serializer_class = RefundSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """환불 요청 처리"""
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        user = validated_data["subscription"].user
        subscription = validated_data["subscription"]

        try:
            with transaction.atomic():
                # 환불 서비스 실행
                service = RefundService(user, subscription)
                refund_response = service.process_refund()

                # 응답 시리얼라이저 적용
                response_serializer = RefundResponseSerializer(refund_response)
                if "error" in refund_response:
                    return Response(
                        response_serializer.data, status=status.HTTP_400_BAD_REQUEST
                    )

                return Response(response_serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"🚨 환불 처리 중 오류 발생: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

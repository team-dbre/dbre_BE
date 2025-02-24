import hashlib
import hmac
import json
import logging
import re

from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from tally.models import Tally
from tally.serializers import TallyWebhookSerializer
from user.models import CustomUser


logger = logging.getLogger(__name__)


def format_phone_number(phone: str) -> str:
    """
    국제 형식(+821012345678)을 한국 표준 전화번호 형식(010-1234-5678)으로 변환
    """
    if phone.startswith("+82"):
        phone = "0" + phone[3:]

    phone = re.sub(r"(\d{3})(\d{4})(\d{4})", r"\1-\2-\3", phone)
    return phone


@extend_schema(tags=["tally"])
@method_decorator(csrf_exempt, name="dispatch")
class TallyWebhookAPIView(APIView):

    permission_classes = [AllowAny]  # 웹훅은 인증 없이 접근 가능
    serializer_class = TallyWebhookSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> JsonResponse:
        """탈리 웹훅 데이터 수신 및 처리"""

        # 웹훅 검증: X-Tally-Signature 확인
        # signing_secret = settings.TALLY_SIGNING_SECRET
        # signature = request.headers.get("X-Tally-Signature")
        request_body = request.body.decode("utf-8")
        logger.warning(f" Received Webhook: {request_body}")

        # logger.warning(f"Received Webhook: {request_body}")
        # logger.warning(f"X-Tally-Signature: {signature}")
        #
        # if not signature:
        #     return Response({"error": "Unauthorized request - Missing Signature"}, status=status.HTTP_403_FORBIDDEN)
        #
        # request_body = request.body.decode("utf-8")
        # calculated_signature = hmac.new(
        #     signing_secret.encode("utf-8"), request_body.encode("utf-8"), hashlib.sha256
        # ).hexdigest()
        #
        # if not hmac.compare_digest(calculated_signature, signature):
        #     return Response({"error": "Unauthorized request - Invalid Signature"}, status=status.HTTP_403_FORBIDDEN)

        # 요청 데이터 파싱
        try:
            data = json.loads(request_body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON format")
            return JsonResponse({"error": "Invalid JSON data"}, status=400)

        form_data = data.get("data", {})
        form_id = form_data.get("formId")
        form_name = form_data.get("formName")
        response_id = form_data.get("responseId")
        fields = form_data.get("fields", [])

        if not form_id or not response_id or not fields:
            logger.error("Missing required fields: formId, responseId, fields")
            return JsonResponse({"error": "잘못된 데이터 형식입니다."}, status=400)

        # 유저 매칭 (이메일 및 전화번호 기준)
        email, name, phone = None, None, None
        additional_data = {}

        for item in fields:
            label = item.get("label", "").strip().lower()
            value = item.get("value", "")

            logger.info(f"Checking field - Label: {label}, Value: {value}")

            if "email" in label or "이메일" in label:
                email = value
            elif "성함" in label or "이름" in label:
                name = value
            elif "연락처" in label or "phone" in label:
                phone = format_phone_number(value)  # 전화번호 변환
            else:
                additional_data[label] = value  # 기타 필드는 추가 정보로 저장

        logger.info(f"Extracted Email: {email}, Phone: {phone}")

        if not email and not phone:
            logger.error("Email or Phone field is missing in the submission")
            return JsonResponse(
                {"error": "이메일 또는 전화번호 정보가 없습니다."}, status=400
            )

        # 유저 존재 여부 확인 (전화번호 or 이메일 기준)
        user = None
        if phone:
            user = CustomUser.objects.filter(phone=phone).first()
        if not user and email:
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "name": name or "Unknown",
                    "phone": phone or None,
                    "sub_status": "none",
                },
            )
            if created:
                logger.info(f"Created new user: {email}")

        if not user:
            return JsonResponse({"error": "유저를 찾을 수 없습니다."}, status=404)

        # 폼 응답 저장
        try:
            Tally.objects.create(
                user=user,
                form_id=form_id,
                form_name=form_name,
                response_id=response_id,
                submitted_at=now(),
                form_data=additional_data,
                created_at=now(),
            )
            logger.info(f"Form submission saved: {response_id}")
        except Exception as e:
            logger.error(f"Database save error: {e}")
            return JsonResponse(
                {"error": "폼 데이터를 저장하는 중 오류 발생"}, status=500
            )

        return JsonResponse({"message": "폼 데이터가 저장되었습니다."}, status=201)

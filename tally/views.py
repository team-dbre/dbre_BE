import hashlib
import hmac
import json
import logging

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


@extend_schema(tags=["tally"], request=TallyWebhookSerializer)
@method_decorator(csrf_exempt, name="dispatch")
class TallyWebhookAPIView(APIView):
    """Tally 웹훅 데이터 처리 API"""

    permission_classes = [AllowAny]
    serializer_class = TallyWebhookSerializer  # ✅ serializer 추가

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """탈리 웹훅 데이터 수신 및 처리"""

        # 요청 데이터 검증
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        form_id = data.get("form_id")
        form_name = data.get("form_name")
        response_id = data.get("response_id")
        submitted_at = data.get("submitted_at")
        form_data = data.get("form_data")

        # 유저 매칭 (이메일 기준)
        email = form_data.get("email")
        name = form_data.get("name")
        phone = form_data.get("phone")

        if not email:
            return Response(
                {"error": "이메일 정보가 없습니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        # 유저 존재 여부 확인
        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "name": name or "Unknown",
                "phone": phone or None,
                "sub_status": "none",
            },
        )

        # 폼 응답 저장
        try:
            Tally.objects.create(
                user=user,
                form_id=form_id,
                form_name=form_name,
                response_id=response_id,
                submitted_at=submitted_at,
                form_data=form_data,
            )
        except Exception as e:
            return Response(
                {"error": f"폼 데이터를 저장하는 중 오류 발생: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"message": "폼 데이터가 저장되었습니다."}, status=status.HTTP_201_CREATED
        )

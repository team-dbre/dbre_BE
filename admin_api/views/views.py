from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max, Min, OuterRef, Q
from django.utils import timezone
from django.utils.timezone import now
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from admin_api.models import AdminLoginLog
from admin_api.serializers import (
    AdminLoginSerializer,
    AdminUserSerializer,
    DashboardSerializer,
    SubscriptionHistorySerializer,
    SubscriptionSerializer,
)
from subscription.models import SubHistories, Subs
from subscription.serializers import SubsSerializer


class AdminUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["admin"],
        summary="Create Admin User",
        description="Create a new admin user with is_staff=True (requires superuser)",
        request=AdminUserSerializer,
        responses={
            201: OpenApiResponse(
                response=AdminUserSerializer,
                description="Admin user created successfully",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        if not request.user.is_superuser:
            return Response(
                {"message": "슈퍼유저만 관리자 계정을 생성할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AdminUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {"message": "관리자 계정이 생성되었습니다.", "email": user.email},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminLoginView(TokenObtainPairView):
    serializer_class = AdminLoginSerializer  # type: ignore

    @extend_schema(
        tags=["admin"],
        summary="Admin Login",
        description="Admin login with email and password",
        request=AdminLoginSerializer,
        examples=[
            OpenApiExample(
                "Admin Login Example",
                value={"email": "admin@example.com", "password": "string"},
                request_only=True,
            )
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "access_token": {"type": "string"},
                    "refresh_token": {"type": "string"},
                    "is_superuser": {"type": "boolean"},
                },
            }
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            response = super().post(request, *args, **kwargs)

            if response.status_code == 200:
                access_token = response.data.get("access_token")
                refresh_token = response.data.get("refresh_token")
                response["Authorization"] = f"Bearer {access_token}"

                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                user = serializer.user

                # 관리자 로그인 로그 기록
                AdminLoginLog.objects.create(
                    user=user,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )

                # Redis에 토큰 저장
                cache.set(
                    f"admin_token:{user.id}",
                    {"access_token": access_token, "refresh_token": refresh_token},
                    timeout=cast(
                        timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
                    ).total_seconds(),
                )

            return response

        except serializers.ValidationError as e:
            error_message = e.detail
            if isinstance(error_message, dict) and "non_field_errors" in error_message:
                error_message = error_message["non_field_errors"][0]
            return Response(
                {"message": error_message}, status=status.HTTP_400_BAD_REQUEST
            )

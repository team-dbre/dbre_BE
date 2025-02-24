from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
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
    AdminPasswordChangeSerializer,
    AdminTallyCompleteSerializer,
    AdminTallySerializer,
    AdminUserSerializer,
    DashboardSerializer,
)
from subscription.models import SubHistories, Subs
from tally.models import Tally
from user.models import CustomUser
from user.utils import measure_time


@extend_schema(tags=["admin"])
class DashboardView(APIView):
    """
    대시 보드
    """

    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        # 전체 구독자 수
        total_subscriptions = Subs.objects.exclude(
            user__sub_status__in=[None, "cancelled"]
        ).count()
        # 오늘 일시정지 수
        paused_subscriptions = (
            SubHistories.objects.filter(status="paused", change_date__date=now().date())
            .values("user")
            .distinct()
            .count()
        )
        # 신규 구독 수
        new_subscriptions_today = Subs.objects.filter(
            start_date__date=timezone.now().date()
        ).count()
        # active_subscriptions = Subs.objects.filter(auto_renew=True).count() # 진행 중

        data = {
            "total_subscriptions": total_subscriptions,  # 전체 구독
            # "active_subscriptions": active_subscriptions,  # 진행 중
            "paused_subscriptions": paused_subscriptions,  # 일시 정지
            "new_subscriptions_today": new_subscriptions_today,  # 오늘 신규 구독
        }

        serializer = DashboardSerializer(instance=data)

        return Response(serializer.data, status=status.HTTP_200_OK)


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

    @extend_schema(
        tags=["admin"],
        summary="Change Admin User Password",
        description="Change the password of an admin user (requires superuser)",
        request=AdminPasswordChangeSerializer,
        responses={
            200: OpenApiResponse(
                response={"message": str},
                description="Password changed successfully",
            ),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="User not found"),
        },
    )
    def patch(self, request: Request, user_id: UUID | str) -> Response:
        if not request.user.is_superuser:
            raise PermissionDenied(
                "슈퍼유저만 관리자 계정의 비밀번호를 변경할 수 있습니다."
            )

        try:
            user = CustomUser.objects.get(id=user_id, is_staff=True)
        except CustomUser.DoesNotExist:
            return Response(
                {"message": "해당 관리자 계정을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminPasswordChangeSerializer(data=request.data)
        if serializer.is_valid():
            user.set_password(serializer.validated_data["new_password"])
            user.save()
            return Response(
                {"message": "관리자 계정의 비밀번호가 변경되었습니다."},
                status=status.HTTP_200_OK,
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
    @measure_time
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            response = Response(serializer.validated_data)
            response["Authorization"] = (
                f"Bearer {serializer.validated_data['access_token']}"
            )

            # 관리자 로그인 로그 기록
            AdminLoginLog.objects.create(
                user=serializer.user,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

            # Redis에 토큰 저장
            cache.set(
                f"admin_token:{serializer.user.id}",
                {
                    "access_token": serializer.validated_data["access_token"],
                    "refresh_token": serializer.validated_data["refresh_token"],
                },
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
                {"error": error_message}, status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(summary="admin 작업 요청 관리", tags=["admin"])
class AdminTallyView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminTallySerializer

    def get(self, request: Request) -> Response:
        """작업 요청 관리"""
        tally = Tally.objects.select_related("user").all()
        serializer = AdminTallySerializer(tally, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminTallyCompleteView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="작업 완료 처리",
        tags=["admin"],
        request=AdminTallyCompleteSerializer,
        responses={200: OpenApiResponse()},
    )
    def post(self, request: Request) -> Response:
        """작용 완료 처리"""
        serializer = AdminTallyCompleteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        tally_id = serializer.validated_data["tally_id"]
        tally = get_object_or_404(Tally, id=tally_id)
        tally.complete = True
        tally.save(update_fields=["complete"])
        return Response({"complete": True}, status=status.HTTP_200_OK)

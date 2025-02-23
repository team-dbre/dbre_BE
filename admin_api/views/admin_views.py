from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
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
    AdminTallyCompleteSerializer,
    AdminTallySerializer,
    AdminUserSerializer,
    DashboardSerializer,
)
from payment.models import Pays
from reviews.models import Review
from subscription.models import SubHistories, Subs
from tally.models import Tally
from user.utils import measure_time


@extend_schema(tags=["admin"])
class DashboardView(APIView):
    """
    대시 보드
    """

    permission_classes = [IsAdminUser]
    serializer_class = DashboardSerializer

    def get(self, request: Request) -> Response:
        """작업 요청 현황"""
        # 오늘 신규 요청
        new_request_today = Tally.objects.filter(
            submitted_at__date=now().date()
        ).count()
        # 미완료
        request_incomplete = Tally.objects.filter(complete=False).count()
        # 완료
        request_complete = Tally.objects.filter(complete=True).count()
        """상담 예약 현황"""
        """구독 현황"""
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
        """구독 취소 현황"""
        # 전체 취소
        subs_cancel_all = SubHistories.objects.filter(status="refund_pending").count()
        # 오늘 취소
        subs_cancel_today = SubHistories.objects.filter(
            status="refund_pending", change_date=now().today()
        ).count()
        """리뷰 현황"""
        all_reviews = Review.objects.all().count()
        new_reviews = Review.objects.filter(created_at__date=now().date()).count()
        """고객 현황"""
        """매출 현황"""
        monthly_sales = (
            Pays.objects.filter(paid_at__month=now().date().month).aggregate(
                total_amount=Sum("amount")
            )["total_amount"]
            or 0
        )
        monthly_refunds = (
            Pays.objects.filter(refund_at__month=now().date().month).aggregate(
                total_refund=Sum("refund_amount")
            )["total_refund"]
            or 0
        )
        monthly_total_sales = monthly_sales - monthly_refunds

        data = {
            "new_request_today": new_request_today,  # 오늘 신규 요청
            "request_incomplete": request_incomplete,  # 미완료
            "request_complete": request_complete,  # 완료
            "total_subscriptions": total_subscriptions,  # 전체 구독
            "paused_subscriptions": paused_subscriptions,  # 일시 정지
            "new_subscriptions_today": new_subscriptions_today,  # 오늘 신규 구독
            "subs_cancel_all": subs_cancel_all,  # 구독 전체 취소
            "subs_cancel_today": subs_cancel_today,  # 구독 오늘 취소
            "all_reviews": all_reviews,  # 전체 리뷰
            "new_reviews": new_reviews,  # 오늘 리뷰
            "monthly_sales": monthly_sales,  # 당월 매출
            "monthly_refunds": monthly_refunds,  # 당월 취소 매출
            "monthly_total_sales": monthly_total_sales,  # 당월 총 매출
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
        # 오늘 신규 요청
        new_request_today = Tally.objects.filter(
            submitted_at__date=now().date()
        ).count()
        # 미완료
        request_incomplete = Tally.objects.filter(complete=False).count()
        # 완료
        request_complete = Tally.objects.filter(complete=True).count()

        tally = Tally.objects.select_related("user").all()
        serializer = AdminTallySerializer(tally, many=True)
        return Response(
            {
                "dashboard": {
                    "new_request_today": new_request_today,  # 오늘 신규 요청
                    "request_incomplete": request_incomplete,  # 미완료
                    "request_complete": request_complete,  # 완료
                },
                "requests": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


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

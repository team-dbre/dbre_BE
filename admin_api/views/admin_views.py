from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.timezone import now
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from admin_api.models import AdminLoginLog
from admin_api.serializers import (
    AdminLoginLogSerializer,
    AdminLoginSerializer,
    AdminPasswordChangeSerializer,
    AdminTallyCompleteSerializer,
    AdminTallySerializer,
    AdminUserListSerializer,
    AdminUserSerializer,
    DashboardSerializer,
)
from payment.models import Pays
from reviews.models import Review
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
        total_subscriptions = Subs.objects.filter(
            user__sub_status__in=["active"]
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
            status="refund_pending", change_date__date=now().date()
        ).count()
        """리뷰 현황"""
        all_reviews = Review.objects.all().count()
        new_reviews = Review.objects.filter(created_at__date=now().date()).count()
        """고객 현황"""
        # 전체 고객 수 (is_staff=False인 경우만)
        total_customers = CustomUser.objects.filter(is_staff=False).count()
        # 오늘 가입한 고객 수
        new_customers_today = CustomUser.objects.filter(
            is_staff=False, created_at__date=now().date()
        ).count()
        # 오늘 탈퇴한 고객 수
        deleted_customers_today = CustomUser.objects.filter(
            is_staff=False, deleted_at__date=now().date()
        ).count()
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
            "total_customers": total_customers,  # 전체 회원 수
            "new_customers_today": new_customers_today,  # 오늘 가입자 수
            "deleted_customers_today": deleted_customers_today,  # 오늘 탈퇴 요청 수
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

    @extend_schema(
        tags=["admin"],
        summary="Change Admin User Password",
        description="Change the password of the logged-in admin user (requires superuser)",
        request=AdminPasswordChangeSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
        },
    )
    def patch(self, request: Request) -> Response:
        if not request.user.is_staff:
            raise PermissionDenied(
                "관리자만 관리자 계정의 비밀번호를 변경할 수 있습니다."
            )

        serializer = AdminPasswordChangeSerializer(data=request.data)
        if serializer.is_valid():
            request.user.set_password(serializer.validated_data["new_password"])
            request.user.save()
            return Response(
                {"message": "관리자 계정의 비밀번호가 변경되었습니다."},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["admin"],
        summary="관리자 계정 목록을 조회",
        description="staff(master, admin) 전체 조회(master 만 가능함)",
        responses={
            200: OpenApiResponse(
                response=AdminUserListSerializer(many=True),
                description="관리자 계정 목록 조회 성공",
            ),
            403: OpenApiResponse(description="권한 없음"),
        },
    )
    def get(self, request: Request) -> Response:
        if not request.user.is_superuser:
            return Response(
                {"message": "슈퍼유저만 관리자 계정 목록을 조회할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        admin_users = CustomUser.objects.filter(is_staff=True)
        serializer = AdminUserListSerializer(admin_users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["admin"],
        summary="지정된 ID의 관리자 계정을 삭제",
        description="staff(admin) 계정 삭제 (master만 가능)",
        parameters=[
            OpenApiParameter(
                name="id",
                description="삭제할 staff의 ID",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
            )
        ],
        responses={
            204: OpenApiResponse(description="계정 삭제 성공"),
            403: OpenApiResponse(description="권한 없음"),
            404: OpenApiResponse(description="해당 ID의 staff 계정을 찾을 수 없음"),
        },
    )
    def delete(self, request: Request) -> Response:
        if not request.user.is_superuser:
            return Response(
                {"message": "슈퍼유저만 관리자 계정을 삭제할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        id = request.query_params.get("id")
        if not id:
            return Response(
                {"message": "삭제할 staff의 ID를 제공해야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            staff_user = get_object_or_404(CustomUser, id=id, is_staff=True)

            if staff_user.is_superuser:
                return Response(
                    {"message": "Master 계정은 삭제할 수 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            staff_user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        except NotFound:
            return Response(
                {"message": "해당 ID의 staff 계정을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )


class AdminLoginView(TokenObtainPairView):
    serializer_class = AdminLoginSerializer  # type: ignore

    @staticmethod
    def get_client_ip(request: Request) -> str:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = str(x_forwarded_for.split(",")[0])
        else:
            ip = str(
                request.META.get("HTTP_X_REAL_IP")
                or request.META.get("REMOTE_ADDR")
                or ""
            )
        return ip

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
                ip_address=self.get_client_ip(request),
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


@extend_schema(tags=["admin"])
class AdminLoginLogListView(generics.ListAPIView):
    serializer_class = AdminLoginLogSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self) -> QuerySet[AdminLoginLog]:
        return AdminLoginLog.objects.all().order_by("-login_datetime")

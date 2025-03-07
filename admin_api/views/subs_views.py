import logging

from typing import Any

from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.timezone import now
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_api.serializers import (
    AdminCancelReasonSerializer,
    AdminRefundInfoSerializer,
    AdminRefundSerializer,
    SubsCancelSerializer,
    SubscriptionHistorySerializer,
    SubscriptionSerializer,
)
from payment.models import Pays
from payment.services.payment_service import RefundService
from subscription.models import SubHistories, Subs


logger = logging.getLogger(__name__)


@extend_schema(tags=["admin"], summary="구독 현황 관리")
class SubscriptionListView(APIView):
    """구독 현황 관리"""

    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionSerializer

    def get(self, request: Request) -> Response:
        # 전체 구독자 수
        total_subscriptions = Subs.objects.filter(user__sub_status="active").count()
        # 오늘 일시정지 수
        paused_subscriptions = (
            SubHistories.objects.filter(
                status="paused", change_date__date=timezone.now().date()
            )
            .values("user")
            .distinct()
            .count()
        )
        # 신규 구독 수
        new_subscriptions_today = Subs.objects.filter(
            start_date__date=timezone.now().date()
        ).count()

        status_filter = request.GET.get("status")
        plan_filter = request.GET.get("plan")
        search_query = request.GET.get("search")
        sort_by = request.GET.get("sort") or "change_date"
        order = request.GET.get("order") or "desc"

        subscriptions = Subs.objects.filter(user__sub_status__in=["active", "pause"])

        if status_filter in ["active", "pause"]:
            subscriptions = subscriptions.filter(user__sub_status=status_filter)

        if plan_filter:
            subscriptions = subscriptions.filter(plan__plan_name=plan_filter)

        if search_query:
            subscriptions = subscriptions.filter(
                Q(user__name__icontains=search_query)
                | Q(user__email__icontains=search_query)
            )

        if sort_by == "user_name" or sort_by == "name":
            sort_by = "user__name"
        elif sort_by == "user_email" or sort_by == "email":
            sort_by = "user__email"
        elif sort_by == "user_phone" or sort_by == "phone":
            sort_by = "user__phone"
        elif sort_by == "user_status" or sort_by == "status":
            sort_by = "user__sub_status"
        elif sort_by == "expiry_date":
            sort_by = "end_date"

        # 첫 구독일 기준 정렬 (히스토리에서 가져옴)
        if sort_by == "change_date":
            subscriptions = subscriptions.annotate(
                first_change_date=SubHistories.objects.filter(sub=OuterRef("id"))
                .order_by("-change_date")
                .values("change_date")[:1]
            ).order_by(f"{'-' if order == 'desc' else ''}first_change_date")
        else:
            order_by_field = f"-{sort_by}" if order == "desc" else sort_by
            subscriptions = subscriptions.order_by(order_by_field)

        serializer = SubscriptionSerializer(subscriptions, many=True)
        return Response(
            {
                "dashboard": {
                    "total_subscriptions": total_subscriptions,
                    "paused_subscriptions": paused_subscriptions,
                    "new_subscriptions_today": new_subscriptions_today,
                },
                "requests": serializer.data,
            },
            status=200,
        )


@extend_schema(
    tags=["admin"],
    summary="특정 사용자 구독 변경 이력 조회",
    request=SubscriptionHistorySerializer,
    parameters=[
        OpenApiParameter(
            name="user_id",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="조회할 사용자의 ID",
        )
    ],
)
class SubscriptionHistoryListView(APIView):
    """특정 사용자 구독 변경 이력 조회"""

    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionHistorySerializer

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response({"error": "user_id가 필요합니다."}, status=400)

        histories = SubHistories.objects.filter(sub__user_id=user_id).order_by(
            "-change_date"
        )
        serializer = SubscriptionHistorySerializer(histories, many=True)

        return Response({"history": serializer.data})


@extend_schema(tags=["admin"], summary="구독 취소 및 환불 리스트")
class AdminRefundPendingListView(APIView):

    permission_classes = [IsAdminUser]
    serializer_class = SubsCancelSerializer

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """구독 취소 및 환불 리스트"""
        # 전체 취소
        subs_cancel_all = SubHistories.objects.filter(status="refund_pending").count()
        # 오늘 취소
        subs_cancel_today = SubHistories.objects.filter(
            status="refund_pending", change_date__date=now().date()
        ).count()

        latest_change_date = (
            SubHistories.objects.filter(
                sub__user=OuterRef("sub__user"),
                sub__user__sub_status__in=["refund_pending", "cancelled"],
            )
            .order_by("-change_date")
            .values("change_date")[:1]
        )

        latest_histories = SubHistories.objects.filter(
            change_date=Subquery(latest_change_date),
            sub__user__sub_status__in=["refund_pending", "cancelled"],
        ).select_related("sub", "sub__user")

        serializer = SubsCancelSerializer(latest_histories, many=True)
        return Response(
            {
                "dashboard": {
                    "sub_cancel_all": subs_cancel_all,
                    "sub_cancel_today": subs_cancel_today,
                },
                "requests": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["admin"],
    request=AdminRefundSerializer,
    summary="관리자가 환불 금액 입력 후 승인",
)
class AdminRefundView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminRefundSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """관리자가 환불 금액 입력 후 승인하는 api"""
        serializer = AdminRefundSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        subscription_id = serializer.validated_data["subscription_id"]
        refund_amount = serializer.validated_data["refund_amount"]

        try:
            subscription = Subs.objects.get(
                id=subscription_id, user__sub_status="refund_pending"
            )
        except Subs.DoesNotExist:
            return Response(
                {"error": "결제 정보를 찾을 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = (
                Pays.objects.filter(
                    user=subscription.user, subs=subscription, status="PAID"
                )
                .order_by("-paid_at")
                .first()
            )
            if not payment:
                return Response(
                    {"error": "결제 정보를 찾을 수 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            refund_response = RefundService(
                subscription.user, subscription, "Admin 승인 환불", ""
            ).request_refund(payment, refund_amount)
            if "error" in refund_response:
                return Response(refund_response, status=status.HTTP_400_BAD_REQUEST)

            subscription.remaining_bill_date = None
            subscription.next_bill_date = None
            subscription.billing_key = None
            subscription.save(update_fields=["remaining_bill_date", "next_bill_date"])

            subscription.user.sub_status = "cancelled"
            subscription.user.save(update_fields=["sub_status"])

            payment.status = "REFUNDED"
            payment.refund_amount = refund_amount
            payment.refund_at = now()
            payment.save(update_fields=["status", "refund_amount", "refund_at"])

            SubHistories.objects.create(
                sub=subscription,
                user=subscription.user,
                status="cancel",
                change_date=now(),
                plan=subscription.plan,
                cancelled_reason="관리자 승인 환불",
                other_reason="",
            )

            return Response(
                {
                    "message": "환불 승인 완료",
                    "refund_amount": refund_amount,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"관리자 환불 승인 중 오류 발생: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(summary="취소 사유 카운트", tags=["admin"])
class AdminCancelReasonView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminCancelReasonSerializer

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """구독 취소 사유 카운트 조회"""
        cancel_count = (
            SubHistories.objects.filter(status="refund_pending")
            .values("cancelled_reason")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        serializer = AdminCancelReasonSerializer(cancel_count, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["admin"],
    responses=AdminRefundInfoSerializer,
    summary="환불 승인 전 결제 정보 확인",
)
class AdminRefundInfoView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminRefundInfoSerializer

    def get(
        self, request: Request, subs_id: int, *args: Any, **kwargs: Any
    ) -> Response:
        """환불 승인 전 결제 정보 확인 조회하는 API (환불 팝업)"""

        try:
            subscription = Subs.objects.get(
                id=subs_id, user__sub_status="refund_pending"
            )
        except Subs.DoesNotExist:
            return Response(
                {"error": "해당 구독이 환불 대기 상태가 아닙니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminRefundInfoSerializer(subscription)
        return Response(serializer.data, status=status.HTTP_200_OK)

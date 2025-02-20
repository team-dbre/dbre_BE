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


@extend_schema(tags=["admin"])
class SubscriptionListView(APIView):
    """
    구독 현황 관리
    """

    def get(self, request: Request) -> Response:
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
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["admin"])
class SubscriptionHistoryListView(APIView):
    """
    특정 사용자 구독 변경 이력 조회
    """

    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        histories = SubHistories.objects.all().order_by("-change_date")
        serializer = SubscriptionHistorySerializer(histories, many=True)
        return Response(serializer.data)


# class SubsCancelledListView(APIView):
#     permission_classes = [IsAdminUser]
#     def get(self, request: Request) -> Response:

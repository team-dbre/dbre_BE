from datetime import timedelta
from typing import Any, cast

from django.utils import timezone
from django.utils.timezone import now
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

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

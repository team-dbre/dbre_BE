# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
#
# from subscription.models import Subs
#
#
# # Create your views here.
# @csrf_exempt
# def subscription_list(request):
#     if request.method == "GET":
#         subscriptions = list(Subs.objects.values())
#         return JsonResponse({"subscriptions": subscriptions}, safe=False)
#     return JsonResponse({"error": "Only GET method allowed"}, status=405
from typing import Optional

from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from subscription.models import SubHistories, Subs
from subscription.serializers import SubsSerializer


class SubsViewSet(viewsets.ModelViewSet):
    queryset = Subs.objects.all()
    serializer_class = SubsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        return self.queryset.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def pause(self, request: Request, pk: Optional[int] = None) -> Response:
        """구독 일시 정지"""
        subscription = self.get_object()
        pause_date = request.data.get("pause_date")

        if not pause_date:
            return Response(
                {"error": "pause_date is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        subscription.remaining_period = subscription.end_date - subscription.start_date
        subscription.end_date = None  # 일시정지로 인해 만료일 제거
        subscription.save()

        SubHistories.objects.create(
            sub=subscription,
            user=request.user,
            plan_id=subscription.id,  # Plan ID를 예시로 저장
            status="pause",
        )

        return Response(
            {
                "user_id": request.user.id,
                "subscription_id": subscription.id,
                "status": "paused",
                "pause_date": pause_date,
                "message": "Successfully paused",
            }
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: Optional[int] = None) -> Response:
        """구독 취소"""
        subscription = self.get_object()
        reason = request.data.get("cancelled_reason")
        other_reason = request.data.get("other_reason", "")

        if reason not in dict(Subs.cancelled_reason_choices):
            return Response(
                {"error": "Invalid cancellation reason"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscription.cancelled_reason = reason
        if reason == "other":
            subscription.other_reason = other_reason

        subscription.auto_renew = False
        subscription.save()

        SubHistories.objects.create(
            sub=subscription,
            user=request.user,
            plan_id=subscription.id,
            status="cancel",
        )

        return Response(
            {
                "user_id": request.user.id,
                "subscription_id": subscription.id,
                "status": "cancelled",
                "cancelled_reason": reason,
                "message": "Successfully cancelled",
            }
        )

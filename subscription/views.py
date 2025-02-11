from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from subscription.models import SubHistories, Subs
from subscription.serializers import SubHistorySerializer, SubsSerializer


@extend_schema(tags=["Subscription"])
class SubscriptionView(APIView):
    """
    구독 정보 조회
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="구독 정보 조회",
        description="구독 ID를 기반으로 특정 구독 정보를 조회합니다.",
        responses={
            200: SubsSerializer(many=True),
            403: {"description": "접근 권한 없음"},
            404: {"description": "구독을 찾을 수 없음"},
        },
        request=None,
        parameters=[],
    )
    def get(self, request: Request) -> Response:
        subs = Subs.objects.filter(user_id=request.user.id)

        if not subs.exists():
            return Response(
                {"error": "구독 정보가 없습니다"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = SubsSerializer(subs, many=True)
        return Response(serializer.data)


@extend_schema(tags=["Subscription"])
class SusHistoryView(APIView):
    """
    구독 이력 조회
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Subscription"],
        responses={
            200: SubHistorySerializer(many=True),
        },
    )
    def get(self, request: Request) -> Response:
        subs_history = SubHistories.objects.filter(user_id=request.user.id)
        if not subs_history.exists():
            return Response(
                {"error": "구독 정보가 없습니다"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = SubHistorySerializer(subs_history, many=True)
        return Response(serializer.data)

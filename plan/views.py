from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from plan.models import Plans
from plan.serializers import PlanSerializer


# @csrf_exempt
# def get_plan_details(request: Request, plan_id: int) -> JsonResponse:
#     """특정 요금제 정보 조회 API"""
#     try:
#         plan = get_object_or_404(Plans, id=plan_id)
#         return JsonResponse(
#             {"id": plan.id, "name": plan.plan_name, "price": plan.price}, status=200
#         )
#     except Exception as e:
#         return JsonResponse(
#             {"error": "요금제 정보를 불러올 수 없습니다.", "details": str(e)},
#             status=500,
#         )
@extend_schema(tags=["Plan"])
class PlanListCreateView(APIView):
    """구독 플랜 목록 조회 및 생성"""

    @extend_schema(responses={200: PlanSerializer(many=True)})
    def get(self, request: PlanSerializer) -> Response:
        """구독 플랜 목록 조회"""
        plans = Plans.objects.all()
        serializer = PlanSerializer(plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=PlanSerializer,
        responses={201: PlanSerializer},
        description="새로운 구독 플랜을 생성합니다.",
    )
    def post(self, request: PlanSerializer) -> Response:
        """구독 플랜 생성"""
        serializer = PlanSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Plan"])
class PlanDetailView(APIView):
    """구독 플랜 개별 조회, 수정, 삭제"""

    @extend_schema(request=PlanSerializer, responses={200: PlanSerializer(many=True)})
    def get(self, request: PlanSerializer, plan_id: int) -> Response:
        """구독 플랜 개별 조회"""
        plan = get_object_or_404(Plans, id=plan_id)
        serializer = PlanSerializer(plan)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=PlanSerializer, responses={200: PlanSerializer(many=True)})
    def patch(self, request: PlanSerializer, plan_id: int) -> Response:
        """구독 플랜 수정"""
        plan = get_object_or_404(Plans, id=plan_id)
        serializer = PlanSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(request=PlanSerializer, responses={200: PlanSerializer(many=True)})
    def delete(self, request: PlanSerializer, plan_id: int) -> Response:
        """구독 플랜 비활성화 처리"""
        plan = get_object_or_404(Plans, id=plan_id)
        plan.is_active = False
        plan.save(update_fields=["is_active"])
        return Response(
            {"message": "플랜이 비활성화되었습니다."}, status=status.HTTP_204_NO_CONTENT
        )


@extend_schema(tags=["Plan"])
class PlanActivateView(APIView):
    """
    비활성화된 플랜을 다시 활성화
    """

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(request=PlanSerializer, responses={200: PlanSerializer(many=True)})
    def post(self, request: PlanSerializer, plan_id: int) -> Response:
        """비활성화된 플랜 활성화"""
        plan = get_object_or_404(Plans, id=plan_id)
        plan.is_active = True
        plan.save(update_fields=["is_active"])
        return Response(
            {"message": "플랜이 활성화되었습니다."}, status=status.HTTP_200_OK
        )

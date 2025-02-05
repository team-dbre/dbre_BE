from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request

from plan.models import Plans


@csrf_exempt
def get_plan_details(request: Request, plan_id: int) -> JsonResponse:
    """특정 요금제 정보 조회 API"""
    try:
        plan = get_object_or_404(Plans, id=plan_id)
        return JsonResponse(
            {"id": plan.id, "name": plan.plan_name, "price": plan.price}, status=200
        )
    except Exception as e:
        return JsonResponse(
            {"error": "요금제 정보를 불러올 수 없습니다.", "details": str(e)},
            status=500,
        )

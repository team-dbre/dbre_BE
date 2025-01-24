from typing import Optional

import requests  # type: ignore

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def get_portone_token() -> Optional[str]:
    """포트원 API 토큰 발급"""
    url = "https://api.iamport.kr/users/getToken"
    payload = {
        "imp_key": settings.IMP_API_KEY,
        "imp_secret": settings.IMP_API_SECRET,
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result: dict = response.json()

        # 반환 값의 타입을 명확히 지정하여 mypy 오류 방지
        token = result.get("response", {}).get("access_token", None)

        if isinstance(token, str):
            return token
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Token request failed: {e}")

    return None


def get_token_view(request: HttpRequest) -> JsonResponse:
    token = get_portone_token()
    if token:
        return JsonResponse({"success": True, "token": token})
    else:
        return JsonResponse({"success": False, "message": "토큰 발급 실패"})


def verify_payment(request: HttpRequest) -> JsonResponse:
    """결제 상태 검증"""
    if request.method == "POST":
        imp_uid = request.POST.get("imp_uid")
        token = get_portone_token()

        if not token:
            return JsonResponse({"success": False, "message": "토큰 발급 실패"})

        url = f"https://api.iamport.kr/payments/{imp_uid}"
        headers = {"Authorization": f"Bearer {token}"}

        response = requests.get(url, headers=headers)
        result = response.json()

        if result["code"] == 0:
            payment_info = result["response"]
            if payment_info["status"] == "paid":
                return JsonResponse({"success": True, "message": "결제 검증 성공"})
            else:
                return JsonResponse({"success": False, "message": "결제 상태 불일치"})
        else:
            return JsonResponse({"success": False, "message": "결제 검증 실패"})

    return JsonResponse({"success": False, "message": "잘못된 요청"})


def payment_page(request: HttpRequest) -> HttpResponse:
    return render(request, "payment.html")


# import requests
# import json
# import os
# from django.http import JsonResponse
# from django.shortcuts import render
# from django.views.decorators.csrf import csrf_exempt, csrf_protect
#
# # 환경 변수에서 포트원 API 키 가져오기 (보안 강화)
#
# import json
# import requests
# from django.conf import settings
# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# import logging
# logger = logging.getLogger(__name__)
#
#
# @csrf_protect
# def request_payment(request):
#     if request.method != "POST":
#         return JsonResponse({"error": "Only POST method allowed"}, status=405)
#
#     try:
#         data = json.loads(request.body)
#         logger.info(f"Received payment request: {data}")
#
#     except json.JSONDecodeError:
#         logger.error("Invalid JSON format")
#         return JsonResponse({"error": "Invalid JSON format"}, status=400)
#
#     api_url = f"{settings.PORTONE_API_BASE_URL}/payments/pre-register"
#     headers = {
#         "Authorization": f"PortOne {settings.PORTONE_API_SECRET}",
#         "Content-Type": "application/json"
#     }
#
#     payload = {
#         "merchantPaymentId": "TEST_ORDER_001",
#         "orderName": "테스트 상품",
#         "totalAmount": 10000,
#         "currency": "KRW",
#         "payMethod": "CARD",
#         "customer": {
#             "fullName": "홍길동",
#             "phoneNumber": "01012345678",
#             "email": "test@example.com"
#         },
#         "storeId": settings.PORTONE_STORE_ID,
#         "channelKey": settings.PORTONE_CHANNEL_KEY
#     }
#     logger.info(f"Sending payment request to PortOne API: {payload}")
#
#     try:
#         response = requests.post(api_url, json=payload, headers=headers)
#         response.raise_for_status()
#         logger.info(f"Payment API Response: {response.json()}")
#         return JsonResponse(response.json(), status=200)
#     except requests.exceptions.RequestException as e:
#         logger.error(f"Payment request failed: {e}")
#         return JsonResponse({"error": "Payment request failed", "details": str(e)}, status=500)
#
#
# def payment_test_view(request):
#     return render(request, 'payment_test.html')
#
#
#
# @csrf_exempt
# def verify_payment(request):
#     if request.method != "POST":
#         return JsonResponse({"error": "Only POST method allowed"}, status=405)
#
#     try:
#         data = json.loads(request.body)
#     except json.JSONDecodeError:
#         return JsonResponse({"error": "Invalid JSON format"}, status=400)
#
#     imp_uid = data.get("imp_uid")
#     merchant_uid = data.get("merchant_uid")
#
#     api_url = f"https://api.portone.io/v2/payments/{imp_uid}"
#
#     headers = {
#         "Authorization": f"PortOne {settings.PORTONE_API_SECRET}",
#         "Content-Type": "application/json"
#     }
#
#     try:
#         response = requests.get(api_url, headers=headers)
#         response.raise_for_status()
#         payment_data = response.json()
#
#         if payment_data['status'] == 'paid' and payment_data['merchant_uid'] == merchant_uid:
#             # 결제 성공 처리
#             return JsonResponse({"message": "Payment successful"}, status=200)
#         else:
#             # 결제 실패 처리
#             return JsonResponse({"error": "Payment verification failed"}, status=400)
#     except requests.exceptions.RequestException as e:
#         return JsonResponse({"error": str(e)}, status=500)

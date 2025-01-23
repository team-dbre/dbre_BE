import requests

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render


def get_portone_token():
    """포트원 API 토큰 발급"""
    url = "https://api.iamport.kr/users/getToken"
    payload = {
        "imp_key": settings.IMP_API_KEY,
        "imp_secret": settings.IMP_API_SECRET,
    }

    response = requests.post(url, json=payload)
    result = response.json()

    if result["code"] == 0:
        return result["response"]["access_token"]
    else:
        return None


def get_token_view(request):
    token = get_portone_token()
    if token:
        return JsonResponse({"success": True, "token": token})
    else:
        return JsonResponse({"success": False, "message": "토큰 발급 실패"})


def verify_payment(request):
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


def payment_page(request):
    return render(request, "payment.html")

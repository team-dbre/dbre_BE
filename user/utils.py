from typing import Any, Dict, Optional, cast

import requests

from django.conf import settings


def get_google_access_token(code: str, redirect_uri: str) -> Optional[str]:
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    response = requests.post(token_url, data=data)
    return cast(Optional[str], response.json().get("access_token"))


def get_google_user_info(access_token: str) -> Dict[str, Any]:
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(user_info_url, headers=headers)
    return cast(Dict[str, Any], response.json())


def normalize_phone_number(phone: str) -> str:
    """전화번호를 010-xxxx-xxxx 형식으로 정규화"""
    # 숫자만 추출
    cleaned = "".join(char for char in phone if char.isdigit())

    # 국가 코드(82) 제거
    if cleaned.startswith("82"):
        cleaned = cleaned[2:]

    # 앞의 0이 없는 경우 추가
    if not cleaned.startswith("0"):
        cleaned = "0" + cleaned

    # xxx-xxxx-xxxx 형식으로 변환
    return f"{cleaned[:3]}-{cleaned[3:7]}-{cleaned[7:]}"


# 디버깅을 위해 로그 추가
def format_phone_for_twilio(phone: str) -> str:
    print(f"Original phone: {phone}")  # 입력된 원본 번호
    formatted = phone.replace("-", "")
    cleaned = "".join(char for char in formatted if char.isdigit())
    result = f"+82{cleaned[1:]}" if cleaned.startswith("0") else f"+82{cleaned}"
    print(f"Formatted phone: {result}")  # 변환된 번호
    return result

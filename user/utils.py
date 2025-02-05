from typing import Any, Dict, Optional, cast

import requests

from django.conf import settings


def get_google_access_token(code: str) -> Optional[str]:
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    response = requests.post(token_url, data=data)
    return cast(Optional[str], response.json().get("access_token"))


def get_google_user_info(access_token: str) -> Dict[str, Any]:
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(user_info_url, headers=headers)
    return cast(Dict[str, Any], response.json())

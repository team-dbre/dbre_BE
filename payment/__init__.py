import os

import portone_server_sdk as portone

from django.conf import settings
from portone_server_sdk._generated.payment.billing_key.client import BillingKeyClient
from portone_server_sdk._generated.payment.client import PaymentClient


# 포트원 API 클라이언트 초기화
# secret_key = os.environ.get("IMP_API_SECRET")
# if secret_key is None:
#     raise ValueError("IMP_API_SECRET 환경 변수가 설정되지 않았습니다.")

portone_client = portone.PaymentClient(secret=str(settings.IMP_API_SECRET))
PORTONE_API_URL = "https://api.portone.io/v2"
IMP_API_KEY = settings.IMP_STORE_ID
PORTONE_CHANNEL_KEY = settings.IMP_CHANNEL_KEY
portone_client2 = PaymentClient(secret=settings.IMP_API_SECRET or "")
billing_key_client = BillingKeyClient(secret=settings.IMP_API_SECRET or "")
PORTONE_API_URL2 = "https://api.portone.io/payments"

default_app_config = "payment.apps.PaymentConfig"

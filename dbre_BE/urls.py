"""
URL configuration for dbre_BE1 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from payment.views import get_token_view, payment_page, verify_payment
from term.views import CreateTermAPI, LatestTermsAPI, TermsDetailAPI


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/schema/", SpectacularAPIView.as_view(), name="schema"
    ),  # JSON 스키마 제공
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),  # Swagger UI
    path(
        "api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),  # Redoc UI
    path("get-token/", get_token_view, name="get_token"),
    path("verify-payment/", verify_payment, name="verify_payment"),
    path("payment/", payment_page, name="payment_page"),
    path("term/", CreateTermAPI.as_view(), name="create_term"),
    path(
        "term/latest/", LatestTermsAPI.as_view(), name="latest_term"
    ),  # 가장 최근 데이터 조회
    path(
        "term/<int:id>/", TermsDetailAPI.as_view(), name="term_detail"
    ),  # 특정 ID 데이터 조회
    # path('request-payment/', request_payment, name='request_payment'),
    # path('verify-payment/', verify_payment, name='verify_payment'),
    # path('payment-test/', payment_test_view, name='payment_test'),
]

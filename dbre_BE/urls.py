from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from payment.views import (
    cancel_payment,
    complete_payment,
    get_billing_key,
    get_item,
    payment_page,
    portone_webhook,
    request_payment,
    request_subscription_payment,
    store_billing_key,
)

# from payment.views import payment_page, request_payment, complete_payment, get_item, cancel_payment, store_billing_key, \
#     request_subscription_payment
from plan.views import get_plan_details
from term.views import CreateTermAPI, LatestTermsAPI, TermsDetailAPI
from user.views import EmailCheckView, LoginView, LogoutView, UserRegistrationView


# Term 관련 URL 패턴
term_patterns = [
    path("", CreateTermAPI.as_view(), name="create_term"),
    path("latest/", LatestTermsAPI.as_view(), name="latest_term"),
    path("<int:id>/", TermsDetailAPI.as_view(), name="term_detail"),
]

# Payment 관련 URL 패턴
payment_patterns = [
    path("", payment_page, name="payment_page"),
    path("request/", request_payment, name="request_payment"),
    path("complete/", complete_payment, name="complete_payment"),
    path("item/", get_item, name="get_item"),
    path("cancel/", cancel_payment, name="cancel_payment"),
    path("billing-key/", store_billing_key, name="store_billing_key"),
    path(
        "subscribe/", request_subscription_payment, name="request_subscription_payment"
    ),
    path("billing-key/<str:user_id>/", get_billing_key, name="get_billing_key"),
    path("webhook/", portone_webhook, name="portone_webhook"),
]


# Plan 관련 URL 패턴
plan_patterns = [
    path("<int:plan_id>/", get_plan_details, name="get_plan_details"),
]

# User 관련 URL 패턴
user_patterns = [
    path("signup/", UserRegistrationView.as_view(), name="signup"),
    path("check-email/", EmailCheckView.as_view(), name="check-email"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]

# 메인 URL 패턴
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/term/", include((term_patterns, "term"))),
    path("api/payment/", include((payment_patterns, "payment"))),
    path("api/user/", include((user_patterns, "user"))),
    path("api/plans/", include((plan_patterns, "plan"))),
]

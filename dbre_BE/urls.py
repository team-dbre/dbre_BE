from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from payment.views import (
    GetBillingKeyView,
    PauseSubscriptionView,
    PortOneWebhookView,
    RefundSubscriptionView,
    RequestSubscriptionPaymentView,
    ResumeSubscriptionView,
    StoreBillingKeyView,
    UpdateBillingKeyView,
)
from plan.views import (
    PlanActivateView,
    PlanDeleteView,
    PlanDetailView,
    PlanListCreateView,
)
from subscription.views import SubscriptionView, SusHistoryView
from term.views import CreateTermAPI, LatestTermsAPI, TermsDetailAPI
from user.views import (
    EmailCheckView,
    GoogleCallbackView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    RequestVerificationView,
    SavePhoneNumberView,
    TokenRefreshView,
    UserProfileView,
    UserRegistrationView,
    VerifyPhoneView,
)


# Term 관련 URL 패턴
term_patterns = [
    path("", CreateTermAPI.as_view(), name="create_term"),
    path("latest/", LatestTermsAPI.as_view(), name="latest_term"),
    path("<int:id>/", TermsDetailAPI.as_view(), name="term_detail"),
]

# Payment 관련 URL 패턴
payment_patterns = [
    path(
        "subscribe/",
        RequestSubscriptionPaymentView.as_view(),
        name="request_subscription_payment",
    ),
    path(
        "billing-key/",
        GetBillingKeyView.as_view(),
        name="get_billing_key",
    ),
    path("webhook/", PortOneWebhookView.as_view(), name="portone_webhook"),
    path("billing-key/", StoreBillingKeyView.as_view(), name="store-billing-key"),
    path("refund/", RefundSubscriptionView.as_view(), name="refund_subscription"),
    path("pause/", PauseSubscriptionView.as_view(), name="pause_subscription"),
    path("resume/", ResumeSubscriptionView.as_view(), name="resume_subscription"),
    path(
        "update-billing-key/", UpdateBillingKeyView.as_view(), name="update_billing_key"
    ),
]


# plan 관련 URL 패턴
plan_patterns = [
    # path("<int:plan_id>/", get_plan_details, name="get_plan_details"),
    path("", PlanListCreateView.as_view(), name="plan-list-create"),
    path("<int:plan_id>/", PlanDetailView.as_view(), name="plan-detail"),
    path("<int:plan_id>/delete/", PlanDeleteView.as_view(), name="plan-delete"),
    path("<int:plan_id>/active/", PlanActivateView.as_view(), name="plan-active"),
]

# subscription 관련 URL 패턴
subs_patterns = [
    path("", SubscriptionView.as_view(), name="subscription-detail"),
    path("history/", SusHistoryView.as_view(), name="subscription-history"),
]


# User 관련 URL 패턴
user_patterns = [
    path("signup/", UserRegistrationView.as_view(), name="signup"),
    path("check-email/", EmailCheckView.as_view(), name="check-email"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "request-verification/",
        RequestVerificationView.as_view(),
        name="request-verification",
    ),
    path("verify-phone/", VerifyPhoneView.as_view(), name="verify_phone"),
    path("g-phone/", SavePhoneNumberView.as_view(), name="g-phone"),
    path("", UserProfileView.as_view(), name="user-profile"),
    path("refresh_token/", TokenRefreshView.as_view(), name="refresh-token"),
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
    path("api/plans/", include((plan_patterns, "plan"))),
    path("api/subscriptions/", include((subs_patterns, "subscription"))),
    path("api/user/", include((user_patterns, "user"))),
    path("auth/google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("auth/google/callback/", GoogleCallbackView.as_view(), name="google_callback"),
]

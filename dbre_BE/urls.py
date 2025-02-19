from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from admin_api.views import (
    CreateAdminView,
    DashboardView,
    SubscriptionHistoryListView,
    SubscriptionListView,
)
from payment.views import (
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
from reviews.views import ReviewCreateView, ReviewDetailView
from subscription.views import SubscriptionView, SusHistoryView
from term.views import CreateTermAPI, LatestTermsAPI, TermsDetailAPI
from user.views import (
    EmailCheckView,
    GoogleCallbackView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetView,
    RequestVerificationView,
    SavePhoneNumberView,
    TokenRefreshView,
    UserPhoneCheckView,
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
    path("find-email/", UserPhoneCheckView.as_view(), name="find-email"),
    path("password/reset/", PasswordResetView.as_view(), name="password_reset"),
    path("password/change/", PasswordChangeView.as_view(), name="password_change"),
]

# review 관련 URL 패턴
review_patterns = [
    path("", ReviewCreateView.as_view(), name="review_subscription"),
    path("<int:review_id>/", ReviewDetailView.as_view(), name="review_detail"),
]

# Admin 관련 URL 패턴
admin_patterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("create-admin/", CreateAdminView.as_view(), name="create-admin"),
    path("subscriptions/", SubscriptionListView.as_view(), name="subscription-list"),
    path(
        "subscriptions/history/",
        SubscriptionHistoryListView.as_view(),
        name="subscription-history",
    ),
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
    path("api/review/", include((review_patterns, "reviews"))),
    path("api/admin/", include((admin_patterns, "admin_api"))),
    path("auth/google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("auth/google/callback/", GoogleCallbackView.as_view(), name="google_callback"),
]

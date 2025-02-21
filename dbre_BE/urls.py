from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from admin_api.urls import admin_patterns
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
from term.urls import term_patterns
from user.urls import user_patterns
from user.views import GoogleCallbackView, GoogleLoginView


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

# review 관련 URL 패턴
review_patterns = [
    path("", ReviewCreateView.as_view(), name="review_subscription"),
    path("<int:review_id>/", ReviewDetailView.as_view(), name="review_detail"),
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


if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns += [
            path("__debug__/", include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass

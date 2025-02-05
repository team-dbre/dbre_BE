from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from term.views import CreateTermAPI, LatestTermsAPI, TermsDetailAPI
from user.views import (
    EmailCheckView,
    GoogleCallbackView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    UserRegistrationView,
)


# Term 관련 URL 패턴
term_patterns = [
    path("", CreateTermAPI.as_view(), name="create_term"),
    path("latest/", LatestTermsAPI.as_view(), name="latest_term"),
    path("<int:id>/", TermsDetailAPI.as_view(), name="term_detail"),
]

# Payment 관련 URL 패턴
payment_patterns = [
    path("", include("payment.urls")),
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
    path("auth/google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("auth/google/callback/", GoogleCallbackView.as_view(), name="google_callback"),
]

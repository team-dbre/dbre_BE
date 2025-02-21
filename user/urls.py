from django.urls import path

from user.views.authenticated_views import (
    LogoutView,
    PasswordChangeView,
    SavePhoneNumberView,
    UserProfileView,
)
from user.views.public_views import (
    EmailCheckView,
    LoginView,
    PasswordResetView,
    RequestVerificationView,
    TokenRefreshView,
    UserPhoneCheckView,
    UserRegistrationView,
    VerifyPhoneView,
)


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

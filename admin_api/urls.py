# Admin 관련 URL 패턴
from django.urls import path

from admin_api.views.admin_views import DashboardView
from admin_api.views.subs_views import SubscriptionHistoryListView, SubscriptionListView
from admin_api.views.views import AdminLoginView, AdminUserView


admin_patterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("admin/", AdminUserView.as_view(), name="create-admin"),
    path("subscriptions/", SubscriptionListView.as_view(), name="subscription-list"),
    path(
        "subscriptions/history/",
        SubscriptionHistoryListView.as_view(),
        name="subscription-history",
    ),
    path("login/", AdminLoginView.as_view(), name="admin-login"),
]

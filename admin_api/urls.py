# Admin 관련 URL 패턴
from django.urls import path

from admin_api.views.admin_views import (
    AdminLoginView,
    AdminTallyCompleteView,
    AdminTallyView,
    AdminUserView,
    DashboardView,
)
from admin_api.views.pay_views import AdminSalesPayView
from admin_api.views.subs_views import (
    AdminCancelReasonView,
    AdminRefundPendingListView,
    AdminRefundView,
    SubscriptionHistoryListView,
    SubscriptionListView,
)


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
    path(
        "subscriptions/cancelled/",
        AdminRefundPendingListView.as_view(),
        name="admin-구독 취소 관리 페이지",
    ),
    path("refund-approve/", AdminRefundView.as_view(), name="admin-환불 승인 post api"),
    path(
        "cancel-reasons/count/",
        AdminCancelReasonView.as_view(),
        name="구독 취소 사유 count",
    ),
    path("tally/", AdminTallyView.as_view(), name="탈리"),
    path("tally/complete/", AdminTallyCompleteView.as_view(), name="탈리 완료 처리"),
    path("sales/", AdminSalesPayView.as_view(), name="매출 관리"),
]

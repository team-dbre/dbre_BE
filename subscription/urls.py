from django.urls import include, path
from rest_framework.routers import DefaultRouter

from subscription.views import SubsViewSet


router = DefaultRouter()
router.register(r"subscriptions", SubsViewSet)


urlpatterns = [
    path("", include(router.urls)),
]

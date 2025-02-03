from django.urls import path

from .views import complete_payment, get_item, payment_page, request_payment


urlpatterns = [
    path("", payment_page, name="payment_page"),
    path("request/", request_payment, name="request_payment"),
    path("complete/", complete_payment, name="complete_payment"),
    path("item/", get_item, name="get_item"),
]

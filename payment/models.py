import uuid

from django.db import models

from subscription.models import Subs
from user.models import CustomUser


# Create your models here.
class Pays(models.Model):
    pays_choices = [
        ("PAID", "Paid"),
        ("CANCELLED", "Cancelled"),
        ("REFUNDED", "Refunded"),
    ]
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    subs = models.ForeignKey(Subs, on_delete=models.CASCADE)
    imp_uid = models.CharField(max_length=255, unique=True)
    merchant_uid = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(decimal_places=2, max_digits=10)
    refund_amount = models.DecimalField(decimal_places=2, max_digits=10, null=True)
    status = models.CharField(max_length=10, choices=pays_choices, default="PAID")
    paid_at = models.DateTimeField(auto_now_add=True)
    refund_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.amount} {self.status}"


class BillingKey(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    billing_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    card_name = models.CharField(max_length=20, null=True, blank=True)
    card_number = models.CharField(max_length=30, null=True, blank=True)

    def __str__(self) -> str:
        return f"BillingKey for {self.user.email}"

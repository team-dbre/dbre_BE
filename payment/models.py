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
    status = models.CharField(max_length=10, choices=pays_choices, default="PAID")
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.amount} {self.status}"

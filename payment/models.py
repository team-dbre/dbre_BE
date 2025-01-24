import uuid

from django.db import models

from subscription.models import Subs


# Create your models here.
class Pays(models.Model):
    pays_choices = [
        ("PAID", "Paid"),
        ("CANCELLED", "Cancelled"),
        ("REFUNDED", "Refunded"),
    ]
    # user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    sub_id = models.ForeignKey(Subs, on_delete=models.CASCADE)
    imp_uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    merchant_uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    amount = models.DecimalField(decimal_places=2, max_digits=10)
    status = models.CharField(max_length=10, choices=pays_choices, default="PAID")
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.amount} {self.status}"

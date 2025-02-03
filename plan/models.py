from django.db import models


class Plans(models.Model):
    PERIOD_CHOICES = [("monthly", "월간"), ("yearly", "연간")]
    id = models.AutoField(primary_key=True)
    plan_name = models.CharField(max_length=100)
    price = models.BigIntegerField()
    period = models.CharField(choices=PERIOD_CHOICES, max_length=10)
    is_active = models.BooleanField(default=True)

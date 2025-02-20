import uuid

from datetime import date, timedelta
from typing import Any, Optional

from django.db import models
from django.utils.timezone import now
from gunicorn.config import User

from plan.models import Plans
from user.models import CustomUser


class Subs(models.Model):
    cancelled_reason_choices = [
        ("expensive", "가격이 비싸서"),
        ("quality", "퀄리티가 마음에 들지 않아서"),
        ("slow_communication", "소통이 느려서"),
        ("hire_full_time", "정직원을 구하는 것이 더 편해서"),
        ("budget_cut", "회사 예산이 줄어들어서"),
        ("other", "기타"),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plans, on_delete=models.CASCADE)
    billing_key = models.ForeignKey(
        "payment.BillingKey", on_delete=models.SET_NULL, null=True, blank=True
    )
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    next_bill_date = models.DateTimeField(null=True, blank=True)
    remaining_bill_date = models.DurationField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False, null=True)
    cancelled_reason = models.CharField(
        max_length=50, choices=cancelled_reason_choices, null=False
    )
    other_reason = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="기타 사유 (상세입력)"
    )

    def __str__(self) -> str:
        start_str = self.start_date.strftime("%Y-%m-%d") if self.start_date else "N/A"
        end_str = self.end_date.strftime("%Y-%m-%d") if self.end_date else "N/A"
        return f"구독 기간: {start_str} - {end_str}"

    @property
    def remaining_days(self) -> int:
        """남은 구독 일수 계산"""
        if self.end_date:
            remaining_time = self.end_date - now()
            return max(0, remaining_time.days)
        return 0

    def calculate_next_bill_date(self) -> Optional[date]:
        if self.plan.period == "monthly":
            return self.start_date + timedelta(days=30)
        elif self.plan.period == "yearly":
            return self.start_date + timedelta(days=365)
        return None

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.next_bill_date:
            self.next_bill_date = self.calculate_next_bill_date()
        super().save(*args, **kwargs)


class SubHistories(models.Model):
    STATUS_CHOICES = [
        ("renewal", "갱신"),
        ("cancel", "취소"),
        ("pause", "정지"),
        ("restart", "재개"),
    ]

    id = models.AutoField(primary_key=True)
    sub = models.ForeignKey(Subs, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plans, on_delete=models.CASCADE)
    change_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    def __str__(self) -> str:
        return f"SubscriptionHistory {self.id} - {self.user.email}"

import uuid

from django.db import models


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
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    next_bill_date = models.DateTimeField()
    remaining_bill_date = models.DateTimeField()
    auto_renew = models.BooleanField(default=False, null=True)
    cancelled_reason = models.CharField(
        max_length=50, choices=cancelled_reason_choices, null=False
    )
    other_reason = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="기타 사유 (상세입력)"
    )

    def __str__(self) -> str:
        return f"구독 기간: {self.start_date.strftime('%Y-%m-%d')} - {self.end_date.strftime('%Y-%m-%d')}"

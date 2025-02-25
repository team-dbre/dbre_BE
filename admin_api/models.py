from typing import Any

from django.db import models

from user.models import CustomUser


class AdminLoginLog(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,  # CASCADE 대신 SET_NULL 사용
        null=True,
        related_name="login_logs",
    )
    email = models.EmailField(null=True, blank=True)
    user_name = models.CharField(max_length=50)  # 사용자 이름 별도 저장
    login_datetime = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255)

    class Meta:
        db_table = "admin_login_logs"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.user:
            self.email = self.user.email
            self.user_name = self.user.name  # 저장 시점의 사용자 이름 기록
        super().save(*args, **kwargs)

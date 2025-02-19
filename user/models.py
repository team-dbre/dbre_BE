import uuid

from typing import Any, Optional

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.validators import RegexValidator
from django.db import models


class CustomUserManager(BaseUserManager):
    def create_user(
        self, email: str, password: Optional[str] = None, **extra_fields: Any
    ) -> "CustomUser":
        if not email:
            raise ValueError("이메일은 필수입니다")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # type: ignore
        user.save(using=self._db)
        return user  # type: ignore

    def create_superuser(
        self, email: str, password: Optional[str] = None, **extra_fields: Any
    ) -> "CustomUser":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    phone_regex = RegexValidator(
        regex=r"^01([0|1|6|7|8|9]?)-?([0-9]{3,4})-?([0-9]{4})$",
        message="전화번호는 '010-1234-5678' 형식으로 입력해주세요.",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=50)
    phone = models.CharField(
        validators=[phone_regex],
        max_length=13,
        unique=True,
        blank=True,
        null=True,
    )
    provider = models.CharField(max_length=20, null=True, blank=True, default=None)
    img_url = models.URLField(null=True, blank=True, default=None)
    sub_status = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("cancelled", "Cancelled"),
            ("paused", "Paused"),
            ("none", "None"),
        ],
        default="none",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "user_users"


class Agreements(models.Model):
    id = models.AutoField(primary_key=True)  # BigIntegerField에서 AutoField로 변경
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    terms_url = models.CharField(max_length=255, null=True, blank=True)
    agreed_at = models.DateTimeField()
    marketing = models.BooleanField()

    class Meta:
        db_table = "user_agreements"

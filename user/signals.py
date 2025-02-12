from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone


UserModel = get_user_model()


@receiver(user_logged_in)
def update_last_login(
    sender: type[AbstractUser], user: AbstractUser, request: Any, **kwargs: Any
) -> None:
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

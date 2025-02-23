from django.db import models
from django.utils.timezone import now

from user.models import CustomUser


class Tally(models.Model):
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="form_submissions"
    )
    form_id = models.CharField(max_length=100)
    form_name = models.CharField(max_length=100)
    response_id = models.CharField(max_length=100, unique=True)
    submitted_at = models.DateTimeField(default=now)
    form_data = models.JSONField()
    complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

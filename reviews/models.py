from django.db import models

from subscription.models import Subs
from user.models import CustomUser


class Review(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    subs = models.ForeignKey(Subs, on_delete=models.CASCADE)
    rating = models.FloatField(null=False)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.content

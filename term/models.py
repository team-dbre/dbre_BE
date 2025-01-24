from django.db import models


# Create your models here.
class Terms(models.Model):
    id = models.AutoField(primary_key=True)  # 기본적으로 AutoField는 자동 증가 정수형
    use = models.TextField()  # Text 필드
    privacy_policy = models.TextField()  # Text 필드
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시 자동으로 시간 저장

    def __str__(self) -> str:
        return f"Terms {self.id}"

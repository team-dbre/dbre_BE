import os

from celery import Celery


# Django settings module 설정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dbre_BE.settings.prod")

app = Celery("dbre_BE")

# namespace='CELERY'는 모든 셀러리 관련 설정 키가 'CELERY_' 로 시작해야 함을 의미
app.config_from_object("django.conf:settings", namespace="CELERY")

# 등록된 Django 앱 설정에서 task 모듈을 불러옴
app.autodiscover_tasks()

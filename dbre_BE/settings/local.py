import os  # CI mypy 통과용

from .base import *


ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False


STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]

INSTALLED_APPS += [
    'django_celery_beat',
    'django_celery_results',
]

CELERY_BROKER_URL = 'redis://localhost:6379/1'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'

from .base import *


# ALLOWED_HOSTS = ["your.domain.com"]
ALLOWED_HOSTS = [
    "desub.kr",
    "api.desub.kr",
    "www.api.desub.kr",
    "localhost",
    "223.130.134.137",
]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False

# 파일 업로드 제한 설정(nginx에도 10MB 제한되어 있음)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB (10 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB

# Celery 설정
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/1')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://redis:6379/1')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'
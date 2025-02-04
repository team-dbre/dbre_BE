from .base import *

DEBUG = False

# ALLOWED_HOSTS = ["your-domain.com"]   # 배포 시
#
# CSRF_COOKIE_HTTPONLY = True
# CSRF_COOKIE_SECURE = True

# -------------------------- 개발환경
ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False

# -------------------------- 개발환경

# SECURE_SSL_REDIRECT = True        # 배포 시
# SESSION_COOKIE_SECURE = True

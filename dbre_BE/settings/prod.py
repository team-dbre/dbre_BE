from .base import *


# ALLOWED_HOSTS = ["your.domain.com"]
ALLOWED_HOSTS = [
    "desub.kr",
    "api.desub.kr",
    "www.api.desub.kr",
    "localhost",
    "223.130.134.137",
    "web",
]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False

# 파일 업로드 제한 설정(nginx에도 10MB 제한되어 있음)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB (10 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB

# INSTALLED_APPS에서 제거
if 'debug_toolbar' in INSTALLED_APPS:
    INSTALLED_APPS.remove('debug_toolbar')

# MIDDLEWARE에서 제거
if 'debug_toolbar.middleware.DebugToolbarMiddleware' in MIDDLEWARE:
    MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')
from .base import *

DEBUG = False

# ALLOWED_HOSTS = ["your-domain.com"]   # 배포 시
#
# CSRF_COOKIE_HTTPONLY = True
# CSRF_COOKIE_SECURE = True

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("DEPLOY_POSTGRES_HOST"),
        "PORT": os.getenv("DEPLOY_POSTGRES_PORT"),
    }
}

STATIC_URL = "staticfiles/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True

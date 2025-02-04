from .base import *


DEBUG = True

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8500",  # 로컬 개발 포트 추가
]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("LOCAL_POSTGRES_HOST"),
        "PORT": os.getenv("LOCAL_POSTGRES_PORT"),
    }
}

STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]

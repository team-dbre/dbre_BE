import os

from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


# 환경별 .env 파일 로드
DJANGO_ENV = os.getenv("DJANGO_ENV", "local")
env_file = f".env.{DJANGO_ENV}"
load_dotenv(env_file)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEBUG = os.getenv("DEBUG", "True")

SECRET_KEY = os.getenv("SECRET_KEY")

IMP_API_KEY = os.getenv("IMP_API_KEY")
IMP_API_SECRET = os.getenv("IMP_API_SECRET")
IMP_MERCHANT_ID = os.getenv("IMP_MERCHANT_ID")
IMP_STORE_ID = os.getenv("STORE_ID")
IMP_API_URL = "https://api.portone.io/"
IMP_CHANNEL_KEY = "channel-key-4ac61816-307a-4820-9e6d-98e4df50a949"
IMP_WEBHOOK_SECRETE = os.getenv("WEB_HOOK_SECRET")
PORTONE_CHANNEL_KEY = os.getenv("PORTONE_CHANNEL_KEY")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
FLOCAL_GOOGLE_REDIRECT_URI = os.getenv("FLOCAL_GOOGLE_REDIRECT_URI")
FPROD_GOOGLE_REDIRECT_URI = os.getenv("FPROD_GOOGLE_REDIRECT_URI")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "payment",
    "term",
    "subscription",
    "user",
    "plan",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]


REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",  # OpenAPI 스키마 자동화
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "dbre_BE.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "dbre_BE.wsgi.application"


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "user.CustomUser"

SITE_ID = 1
# 이메일 로그인을 위한 인증 백엔드 설정
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "email",
    "USER_ID_CLAIM": "email",
}

# 공통 데이터베이스 설정
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT"),
    }
}

# redis 캐시 설정
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "RETRY_ON_TIMEOUT": True,
        },
        "KEY_PREFIX": "dbre",
    }
}

SPECTACULAR_SETTINGS = {
    "TITLE": "DBre_BE",
    "DESCRIPTION": "DBre project BackEnd part",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {"defaultModelsExpandDepth": 1},
    "EXAMPLES_INCLUDE_SCHEMA": True,
    "TAGS": [
        {"name": "user", "description": "User management operations"},
        {"name": "payment", "description": "Payment related operations"},
        {"name": "subscription", "description": "Subscription related operations"},
        {"name": "plan", "description": "Plan related operations"},
        {"name": "term", "description": "Term related operations"},
    ],
    "OPERATIONS_SORTER": None,
    "TAG_SORTER": None,
}

SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": False,
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Token 형식: 'Bearer {token}'",
        }
    },
    "SECURITY_REQUIREMENTS": [{"Bearer": []}],
}


STATIC_URL = "staticfiles/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")


CORS_ALLOW_ALL_ORIGINS = True  # ⚠️ 배포 시엔 특정 도메인만 허용해야 함

# ✅ 특정 도메인만 허용 (보안 강화 - 운영 환경)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:63342",  # ✅ 브라우저에서 실행한 로컬 HTML 파일
    "http://127.0.0.1:8000",  # ✅ 로컬 Django 서버
    "http://localhost:3000",  # ✅ React/Vue 같은 로컬 프론트엔드 서버
]

# ✅ 인증이 필요한 요청 (예: 쿠키 포함 요청) 허용
CORS_ALLOW_CREDENTIALS = True

# ✅ 특정 HTTP 메서드만 허용
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

# ✅ 특정 헤더만 허용
CORS_ALLOW_HEADERS = ["content-type", "authorization"]

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[%(asctime)s] %(levelname)s - %(name)s - %(message)s"},
        "simple": {"format": "%(levelname)s - %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "payment": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

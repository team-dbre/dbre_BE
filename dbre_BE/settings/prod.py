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

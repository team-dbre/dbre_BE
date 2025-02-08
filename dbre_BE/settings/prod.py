from .base import *


# ALLOWED_HOSTS = ["your.domain.com"]
ALLOWED_HOSTS = ["api.endofday.store", "localhost", "*"]

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
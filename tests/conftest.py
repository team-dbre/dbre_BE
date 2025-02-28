import os

import django

from django.conf import settings


def pytest_configure() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dbre_BE.settings.local")
    django.setup()

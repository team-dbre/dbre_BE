import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dbre_BE.settings.prod")
application = get_wsgi_application()

# 스케줄러 시작
from dbre_BE.scheduler import start


start()

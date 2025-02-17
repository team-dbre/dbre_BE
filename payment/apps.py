import logging

from django.apps import AppConfig


logger = logging.getLogger(__name__)


class PaymentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payment"

    def ready(self) -> None:
        from payment.scheduler import start

        logger.info("PaymentConfig.ready() 실행됨")
        start()

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django_apscheduler.jobstores import DjangoJobStore


logger = logging.getLogger(__name__)


def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # Users 앱의 작업 추가
    from user.tasks import delete_inactive_users

    scheduler.add_job(
        delete_inactive_users,
        trigger="cron",
        hour=5,
        minute=0,
        id="delete_inactive_users",
        replace_existing=True,
    )

    # Payment 앱의 작업 추가
    from payment.tasks import process_scheduled_payments

    scheduler.add_job(
        process_scheduled_payments,
        trigger="interval",
        days=1,
        id="process_scheduled_payments",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started...")
    return scheduler

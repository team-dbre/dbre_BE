import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.utils.timezone import now

from payment.services.payment_service import SubscriptionPaymentService
from subscription.models import Subs


logger = logging.getLogger(__name__)


def process_scheduled_payments() -> str:
    """구독 자동 결제 태스크"""
    today = now()
    subscriptions = Subs.objects.filter(next_bill_date__lte=today, auto_renew=True)

    for sub in subscriptions:
        if not sub.billing_key:
            logger.error(
                f"구독 {sub.user.name} - {sub.plan.plan_name}: Billing Key가 없습니다."
            )
            continue
        service = SubscriptionPaymentService(
            user=sub.user, plan=sub.plan, billing_key=sub.billing_key.billing_key
        )
        try:
            short_payment_id, billing_key_payment_summary = service.process_payment(sub)
            service.save_payment(sub, short_payment_id, billing_key_payment_summary)
            service.schedule_next_payment(sub)
            logger.info(f"구독 갱신 완료: {sub.user.name} - {sub.plan.plan_name}")
        except Exception as e:
            logger.error(f"자동 결제 실패: {e}")

    return f"{subscriptions.count()}개의 구독 갱신 처리 완료"


def start() -> None:
    """APScheduler 실행"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(process_scheduled_payments, trigger=IntervalTrigger(days=1))
    scheduler.start()

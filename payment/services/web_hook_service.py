import logging

from typing import Any, Dict

from dateutil.relativedelta import relativedelta
from django.utils.timezone import now

from payment.models import Pays
from subscription.models import Subs


logger = logging.getLogger(__name__)


class WebhookService:
    """포트원 웹훅 비지니스 모델"""

    def __init__(self, imp_uid: str, status: str, merchant_uid: str) -> None:
        self.imp_uid = imp_uid
        self.status = status
        self.merchant_uid = merchant_uid

    def process_webhook(self) -> Dict[str, Any]:
        """웹훅 이벤트 처리"""
        logger.info(
            f"[Webhook] 처리 시작 - imp_uid: {self.imp_uid}, status: {self.status}, merchant_uid: {self.merchant_uid}"
        )

        # 결제 정보 조회
        payment = Pays.objects.filter(merchant_uid=self.merchant_uid).first()
        if not payment:
            logger.error(
                f"[Webhook] 결제 정보 없음 - Merchant UID: {self.merchant_uid}"
            )
            raise ValueError("Payment not found")

        if self.status == "paid":
            return self._handle_payment_success(payment)

        if self.status in ["failed", "cancelled"]:
            return self._handle_payment_failure(payment)

        logger.warning(f"[Webhook] 처리되지 않은 상태 - Status: {self.status}")
        raise ValueError("Invalid payment status")

    def _handle_payment_success(self, payment: Pays) -> Dict[str, Any]:
        """결제 성공 처리 - 구독 갱신"""
        subscription = Subs.objects.filter(user=payment.user).first()

        if subscription:
            current_bill_date = subscription.next_bill_date or now()
            next_bill_date = current_bill_date + relativedelta(months=1)

            subscription.next_bill_date = next_bill_date
            subscription.auto_renew = True
            subscription.save()

            logger.info(
                f"[Webhook] 결제 성공 - 다음 결제일: {subscription.next_bill_date}"
            )

        return {
            "message": "Payment successful",
            "next_billing_date": (
                subscription.next_bill_date.isoformat()
                if subscription and subscription.next_bill_date
                else None
            ),
        }

    def _handle_payment_failure(self, payment: Pays) -> Dict[str, Any]:
        """결제 실패 처리 - 자동 갱신 해제"""
        payment.status = "FAILED"
        payment.save()

        subscription = Subs.objects.filter(user=payment.user).first()
        if subscription:
            subscription.auto_renew = False
            subscription.save()

        logger.error(f"[Webhook] 결제 실패 - Auto renew 비활성화")
        return {"message": "Payment failed, subscription auto-renew disabled"}

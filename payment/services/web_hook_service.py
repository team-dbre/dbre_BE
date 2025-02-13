import hashlib
import hmac
import logging

from typing import Any, Dict

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils.timezone import now
from rest_framework.request import Request

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


def update_payment_status(
    payment_id: int, status: str, amount: float
) -> dict[str, Any]:
    try:
        pay_record = Pays.objects.get(imp_uid=payment_id)

        # 결제 금액 검증
        if pay_record.amount != amount:
            return {"message": "Amount mismatch", "status": 400}

        if status == "PAID":
            pay_record.status = "PAID"
            pay_record.paid_at = now()
        elif status == "CANCELLED":
            pay_record.status = "CANCELLED"
        elif status == "REFUNDED":
            pay_record.status = "REFUNDED"

        pay_record.save()
        return {"message": "Payment updated successfully", "status": 200}

    except Pays.DoesNotExist:
        return {"message": "Payment not found", "status": 404}
    except Exception as e:
        return {"message": f"Error: {str(e)}", "status": 500}


def verify_signature(request: Request, signature: str) -> bool:
    try:
        # 1. request.body 읽기
        body = request.body.decode("utf-8")
        logger.info(f"Webhook Raw Body: {body}")

        # 2. 요청 헤더에서 x-portone-signature 가져오기
        received_signature = request.headers.get("x-portone-signature")
        if not received_signature:
            logger.error("Missing x-portone-signature header")
            return False

        # 3. Expected Signature 생성
        expected_signature = hmac.new(
            key=settings.IMP_WEBHOOK_SECRETE.encode("utf-8"),  # type: ignore
            msg=body.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # 4. 로그 확인
        logger.info(f" Expected Signature: {expected_signature}")
        logger.info(f" Received Signature: {received_signature}")

        # 5. 검증 결과 반환
        return hmac.compare_digest(expected_signature, received_signature)

    except Exception as e:
        logger.exception(f" Error verifying signature: {e}")
        return False

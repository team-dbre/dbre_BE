import logging
import uuid

from datetime import timedelta
from typing import Any, Dict

from dateutil.relativedelta import relativedelta
from django.utils.timezone import now
from portone_server_sdk._generated.common.billing_key_payment_input import (
    BillingKeyPaymentInput,
)
from portone_server_sdk._generated.common.customer_input import CustomerInput
from portone_server_sdk._generated.common.customer_name_input import CustomerNameInput
from portone_server_sdk._generated.common.payment_amount_input import PaymentAmountInput

from payment import portone_client2
from payment.models import BillingKey, Pays
from subscription.models import SubHistories, Subs


logger = logging.getLogger(__name__)


class SubscriptionPaymentService:
    """정기 결제 처리 비즈니스 로직"""

    def __init__(self, user: Any, plan: Any, billing_key: str) -> None:
        self.user = user
        self.plan = plan
        self.billing_key = billing_key

    def create_subscription(self) -> Subs:
        """구독 정보 생성 (기존 구독이 있으면 반환)"""
        existing_sub = Subs.objects.filter(user=self.user, plan=self.plan).first()
        if existing_sub:
            return existing_sub

        billing_key_obj = BillingKey.objects.get(billing_key=self.billing_key)
        next_billing_date = now() + relativedelta(months=1)
        sub = Subs.objects.create(
            user=self.user,
            plan=self.plan,
            billing_key=billing_key_obj,
            next_bill_date=next_billing_date,
            auto_renew=True,
        )

        return sub

    def process_payment(self, sub: Subs) -> str:
        """포트원 결제 요청 및 처리"""
        if not sub.billing_key:
            raise ValueError("Billing Key is missing for the subscription.")

        billing_key = sub.billing_key.billing_key
        short_payment_id = f"PAY{uuid.uuid4().hex[:18]}"

        customer_info = CustomerInput(
            id=str(sub.user.id),
            email=sub.user.email or "",
            name=CustomerNameInput(full=sub.user.name or "Unnamed User"),
        )

        try:
            response = portone_client2.pay_with_billing_key(
                payment_id=short_payment_id,
                billing_key=billing_key.strip(),
                order_name=sub.plan.plan_name,
                amount=PaymentAmountInput(total=int(sub.plan.price)),
                currency="KRW",
                customer=customer_info,
                bypass={"pgProvider": "kpn"},
            )

            if not response.payment or not response.payment.pg_tx_id:
                raise ValueError("Payment was canceled or failed")

            return response.payment.pg_tx_id

        except Exception as e:
            raise ValueError(f"Payment failed: {str(e)}")

    def save_payment(self, sub: Subs, payment_id: str) -> Pays:
        """결제 내역 저장"""
        payment = Pays.objects.create(
            user=sub.user,
            subs=sub,
            imp_uid=payment_id,
            merchant_uid=f"PAY{uuid.uuid4().hex[:18]}",
            amount=sub.plan.price,
            status="PAID",
        )

        sub.user.sub_status = "active"
        sub.user.save(update_fields=["sub_status"])

        SubHistories.objects.create(
            sub=sub,
            user=sub.user,
            plan=sub.plan,
            change_date=now(),
            status="renewal",
        )

        return payment

    def schedule_next_payment(self, sub: Subs) -> Dict[str, Any]:
        """다음 결제 예약"""
        current_date = now()
        start_date = sub.start_date
        next_billing_date = current_date + relativedelta(months=1)
        scheduled_payment_id = f"SUBS{uuid.uuid4().hex[:18]}"

        if sub.billing_key is None:
            raise ValueError("Billing Key is missing for the subscription.")

        customer_info = CustomerInput(
            id=str(sub.user.id),
            email=sub.user.email or "",
            name=CustomerNameInput(full=sub.user.name or "Unnamed User"),
        )

        try:
            schedule_response = (
                portone_client2.payment_schedule.create_payment_schedule(
                    payment_id=scheduled_payment_id,
                    payment=BillingKeyPaymentInput(
                        billing_key=sub.billing_key.billing_key.strip(),
                        order_name=sub.plan.plan_name,
                        amount=PaymentAmountInput(total=int(sub.plan.price)),
                        currency="KRW",
                        customer=customer_info,
                    ),
                    time_to_pay=next_billing_date.isoformat(),
                )
            )
            # 구독 종료일 계산
            if sub.plan.period == "monthly":
                end_date = start_date + relativedelta(
                    months=1
                )  # 월간 플랜은 1개월 후 종료
            elif sub.plan.period == "yearly":
                end_date = start_date + relativedelta(
                    months=12
                )  # 연간 플랜은 12개월 후 종료
            else:
                raise ValueError("Invalid subscription period")

            # 한 달 단위로 남은 구독 개월 수 계산
            remaining_bill_date = (end_date - current_date).days

            sub.next_bill_date = next_billing_date
            sub.end_date = end_date
            sub.remaining_bill_date = timedelta(days=remaining_bill_date)
            sub.save(
                update_fields=["next_bill_date", "end_date", "remaining_bill_date"]
            )
            return {
                "next_billing_date": next_billing_date.isoformat(),
                "end_date": end_date.isoformat(),
                "remaining_bill_date": remaining_bill_date,
            }

        except Exception as e:
            raise ValueError(f"Failed to schedule next payment: {str(e)}")

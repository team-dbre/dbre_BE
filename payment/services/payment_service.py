import logging
import uuid

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.timezone import now
from portone_server_sdk._generated.common.billing_key_payment_input import (
    BillingKeyPaymentInput,
)
from portone_server_sdk._generated.common.customer_input import CustomerInput
from portone_server_sdk._generated.common.customer_name_input import CustomerNameInput
from portone_server_sdk._generated.common.payment_amount_input import PaymentAmountInput
from portone_server_sdk._generated.payment.billing_key_payment_summary import (
    BillingKeyPaymentSummary,
)

from payment import portone_client2
from payment.models import BillingKey, Pays
from payment.utils import (
    cancel_scheduled_payments,
    create_scheduled_payment,
    delete_billing_key_with_retry,
    fetch_scheduled_payments,
)
from subscription.models import SubHistories, Subs
from user.models import CustomUser


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

        if (
            existing_sub
            and existing_sub.plan == self.plan
            and existing_sub.user.sub_status == "active"
        ):
            raise ValueError(f"이미 {existing_sub.plan}에 구독중입니다.")

        if existing_sub and existing_sub.user.sub_status in ["cancelled", "paused"]:
            existing_sub.user.sub_status = "active"
            existing_sub.plan = self.plan
            existing_sub.billing_key = BillingKey.objects.get(
                billing_key=self.billing_key
            )
            existing_sub.start_date = now()
            existing_sub.next_bill_date = now() + relativedelta(months=1)
            existing_sub.auto_renew = True
            existing_sub.save(
                update_fields=[
                    "plan",
                    "billing_key",
                    "start_date",
                    "next_bill_date",
                    "auto_renew",
                ]
            )
            existing_sub.user.save(update_fields=["sub_status"])

            return existing_sub

        # 신규 구독 생성
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

    def process_payment(self, sub: Subs) -> tuple[str, BillingKeyPaymentSummary]:
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

            return short_payment_id, response.payment

        except Exception as e:
            raise ValueError(f"Payment failed: {str(e)}")

    def save_payment(
        self,
        sub: Subs,
        payment_id: str,
        billing_key_payment_summary: BillingKeyPaymentSummary,
    ) -> Pays:
        """결제 내역 저장"""
        payment = Pays.objects.create(
            user=sub.user,
            subs=sub,
            imp_uid=payment_id,
            merchant_uid=f"PAY{uuid.uuid4().hex[:18]}",
            amount=sub.plan.price,
            status="PAID",
        )
        logger.info(
            f"[Saved Payment] imp_uid: {payment.imp_uid}"
        )  # 저장된 imp_uid 로그 추가

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
        new_start_date = current_date
        next_billing_date = (sub.next_bill_date or current_date) + relativedelta(
            months=1
        )
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
            logger.info(f" [PortOne API] 결제 예약 성공: {schedule_response.__dict__}")

            # 구독 종료일 계산
            if sub.plan.period == "monthly":
                end_date = new_start_date + relativedelta(
                    months=1
                )  # 월간 플랜은 1개월 후 종료
            elif sub.plan.period == "yearly":
                end_date = new_start_date + relativedelta(
                    months=12
                )  # 연간 플랜은 12개월 후 종료
            else:
                raise ValueError("Invalid subscription period")

            # 한 달 단위로 남은 구독 개월 수 계산
            remaining_bill_date = (end_date - current_date).days

            sub.start_date = new_start_date
            sub.next_bill_date = next_billing_date
            sub.end_date = end_date
            sub.remaining_bill_date = timedelta(days=remaining_bill_date)
            sub.save(
                update_fields=[
                    "start_date",
                    "next_bill_date",
                    "end_date",
                    "remaining_bill_date",
                ]
            )
            return {
                "start_date": sub.start_date.isoformat(),
                "next_billing_date": next_billing_date.isoformat(),
                "end_date": end_date.isoformat(),
                "remaining_bill_date": remaining_bill_date,
            }

        except Exception as e:
            raise ValueError(f"Failed to schedule next payment: {str(e)}")


class RefundService:
    """포트원 환불 처리 서비스"""

    def __init__(
        self,
        user: CustomUser,
        subscription: Subs,
        cancel_reason: str,
        other_reason: str,
    ) -> None:
        self.user = user
        self.subscription = subscription
        self.cancel_reason = cancel_reason
        self.other_reason = other_reason

    def get_cancellable_amount(self, payment: Pays) -> float:
        """포트원에서 현재 결제 건의 취소 가능 금액 조회"""
        try:
            payment_info = portone_client2.get_payment(payment_id=payment.imp_uid)
            logger.info(f"[PortOne API] 결제 정보 조회: {payment_info.__dict__}")

            # payment_info가 dict인지 확인 후, amount 필드 접근
            if isinstance(payment_info, dict):
                amount_paid = payment_info.get("amount", {}).get("paid", 0)
                amount_cancelled = payment_info.get("amount", {}).get("cancelled", 0)
            else:
                amount_paid = getattr(payment_info.amount, "paid", 0)
                amount_cancelled = getattr(payment_info.amount, "cancelled", 0)

            # `cancellable_amount` 값이 없으면 대체 값 계산
            cancellable_amount = getattr(payment_info, "cancellable_amount", None)
            if cancellable_amount is None:
                cancellable_amount = (
                    amount_paid - amount_cancelled
                )  # 환불 가능 금액 재계산

            # 이미 취소된 결제인지 확인
            if cancellable_amount <= 0:
                logger.warning(
                    f"[PortOne API] 결제는 이미 취소되었습니다. 추가 환불 불가능."
                )
                raise ValueError("이미 취소된 결제입니다.")

            return float(cancellable_amount)

        except Exception as e:
            logger.error(f"취소 가능 금액 조회 실패: {e}")
            raise ValueError("포트원 API에서 취소 가능 금액을 확인할 수 없습니다.")

    def calculate_refund_amount(self, payment: Pays) -> float:
        """남은 일수를 계산하여 환불 금액 산정"""
        plan_price = self.subscription.plan.price  # 1개월 구독 요금
        start_date = self.subscription.start_date
        end_date = self.subscription.end_date or (start_date + timedelta(days=30))
        total_days = (end_date - start_date).days  # 총 사용 가능 일수
        used_days = (now() - start_date).days  # 사용한 일수
        remaining_days = max(total_days - used_days, 0)  # 남은 일수

        logger.info(
            f"[Refund Calculation] 사용일수: {used_days}, 남은일수: {remaining_days}, 총일수: {total_days}"
        )

        if remaining_days <= 0:
            logger.warning("이미 사용한 일수가 많아 환불할 금액이 없습니다.")
            return 0  # 이미 사용 완료된 구독은 환불 불가

        # 환불 금액 계산 (남은 일수 기준)
        refund_amount = (plan_price / total_days) * remaining_days
        refund_amount = round(refund_amount, 2)  # 소수점 2자리 반올림

        # 현재 취소 가능 금액 확인 (포트원 API)
        cancellable_amount = self.get_cancellable_amount(payment)

        # 요청 환불 금액이 취소 가능 금액보다 크면 자동 조정
        refund_amount = min(refund_amount, cancellable_amount)

        logger.info(
            f"환불 금액 계산: {refund_amount} (사용일수: {used_days}, 남은일수: {remaining_days}, 취소 가능 금액: {cancellable_amount})"
        )
        return refund_amount

    def request_refund(self, payment: Pays, refund_amount: float) -> dict:
        """포트원의 cancel_payment API를 사용하여 결제 취소 및 환불"""

        try:
            cancellable_amount = self.get_cancellable_amount(payment)

            # 취소 가능 금액과 환불 요청 금액이 일치하는지 확인
            if refund_amount > cancellable_amount:
                refund_amount = cancellable_amount  # 취소 가능 금액을 기준으로 조정

            logger.info(
                f"[Refund Request] imp_uid: {payment.imp_uid}, 환불 요청 금액: {refund_amount}"
            )

            response = portone_client2.cancel_payment(
                payment_id=payment.imp_uid,  # `imp_uid`를 `payment_id`로 전달
                amount=int(refund_amount),  # 환불할 금액
                reason="사용자 요청 환불",
                current_cancellable_amount=int(
                    cancellable_amount
                ),  # 취소 가능 금액 동기화
            )

            # 응답 객체를 JSON으로 변환하여 올바른 필드 확인
            response_data = response.__dict__  # 포트원 응답 객체를 딕셔너리로 변환
            logger.info(f"포트원 환불 API 응답: {response_data}")

            # 응답의 `message` 필드를 사용하여 오류 확인
            if hasattr(response, "message") and response.message:
                raise ValueError(f"환불 실패: {response.message}")

            return {"success": True, "refund_amount": refund_amount}

        except Exception as e:
            logger.error(
                f"포트원 환불 API 실패: {str(e)}", exc_info=True
            )  # exc_info=True 로 에러 로그 추가
            return {"error": f"포트원 환불 API 실패: {str(e)}"}

    def cancel_billing_key(self) -> Dict[str, Any]:
        """빌링 키 삭제 (자동 결제 해지 - 미래 예약 결제 취소)"""
        try:
            if self.subscription.billing_key:
                billing_key = self.subscription.billing_key.billing_key
                plan_id = self.subscription.plan.id

                # 예약 결제 조회 함수 호출
                scheduled_payments = fetch_scheduled_payments(billing_key, plan_id)

                if scheduled_payments:
                    logger.info(
                        f"정기 결제 스케줄 발견 (취소 대상 플랜 ID: {plan_id}): {scheduled_payments}, 스케줄 취소 진행."
                    )

                    # 해당하는 스케줄만 취소
                    portone_client2.payment_schedule.revoke_payment_schedules(
                        billing_key=billing_key, schedule_ids=scheduled_payments
                    )
                    logger.info(
                        f"특정 플랜 ({plan_id})에 대한 정기 결제 스케줄 취소 완료."
                    )

                # 빌링키 삭제 요청
                billing_deleted = delete_billing_key_with_retry(billing_key)

                if billing_deleted:
                    logger.info(f"Billing_Key 삭제 성공: {billing_key}")
                    self.subscription.billing_key.delete()
                    return {
                        "success": True,
                        "message": "Billing key deleted successfully",
                    }
                else:
                    logger.warning(f"Billing_Key 삭제 실패: {billing_key}")
                    return {"success": False, "message": "Billing key deletion failed"}

        except Exception as e:
            logger.error(f"빌링키 삭제 실패: {e}")
            return {"success": False, "error": str(e)}

        return {"success": False, "message": "Unexpected error in cancel_billing_key"}

    def process_refund(self) -> Dict[str, Any]:
        """환불 요청 처리 및 빌링 해지"""
        with transaction.atomic():
            try:
                requested_plan = self.subscription.plan
                logger.info(
                    f"요청 된 구독 플랜: {requested_plan.id} {requested_plan.plan_name}"
                )

                payment = (
                    Pays.objects.filter(user=self.user, subs=self.subscription)
                    .order_by("-id")
                    .first()
                )
                if not payment:
                    raise ValueError("환불할 결제 정보를 찾을 수 없습니다.")

                # 요청된 플랜과 결제된 플랜이 일치하는지 확인
                if payment.subs.plan.id != requested_plan.id:
                    logger.error(
                        f" 요청된 플랜({requested_plan.id})과 결제된 플랜({payment.subs.plan.id})가 다릅니다"
                    )
                    raise ValueError(
                        "취소 요청한 구독 플랜과 일치하지 않는 결제건입니다"
                    )

                # 환불 금액 계산
                refund_amount = self.calculate_refund_amount(payment)
                if refund_amount <= 0:
                    raise ValueError("이미 사용한 일수가 많아 환불할 금액이 없습니다.")

                refund_response = self.request_refund(payment, refund_amount)

                # 환불 성공 후 빌링 키 삭제 및 구독 비활성화
                if refund_response["success"]:
                    self.subscription.auto_renew = False
                    self.subscription.cancelled_reason = self.cancel_reason
                    self.subscription.other_reason = self.other_reason
                    self.subscription.save(
                        update_fields=["auto_renew", "cancelled_reason", "other_reason"]
                    )

                    self.subscription.user.sub_status = "cancelled"
                    self.subscription.user.save(update_fields=["sub_status"])

                    SubHistories.objects.create(
                        sub=self.subscription,
                        user=self.user,
                        plan=self.subscription.plan,
                        change_date=now(),
                        status="cancel",
                    )
                    logger.info(
                        f" 구독 히스토리 생성 완료: {self.subscription.user.id}, {self.subscription.plan.plan_name}"
                    )

                    billing_cancelled = self.cancel_billing_key()
                    if billing_cancelled is None:
                        billing_cancelled = False
                        logger.warning("환불은 성공했지만, 빌링키 삭제에 실패했습니다.")
                        return {
                            "message": "환불 성공, 하지만 빌링키 삭제에 실패했습니다.",
                            "refund_amount": refund_amount,
                        }

                    payment.status = "REFUNDED"
                    payment.refund_amount = Decimal(refund_amount)
                    payment.save(update_fields=["status", "refund_amount"])

                    return {
                        "message": "환불 성공",
                        "refund_amount": refund_amount,
                        "cancelled_reason": self.cancel_reason,
                        "other_reason": self.other_reason,
                    }

            except ValueError as e:
                logger.error(f"환불 실패: {str(e)}", exc_info=True)
                return {"error": str(e)}

            except Exception as e:
                logger.error(f"예상치 못한 오류 발생: {str(e)}", exc_info=True)
                return {
                    "error": "예상치 못한 오류가 발생했습니다. 관리자에게 문의하세요."
                }
        logger.warning(" 예상치 못한 실행 경로 발견: process_refund에서 반환되지 않음")
        return {"error": "알 수 없는 오류가 발생했습니다. 관리자에게 문의하세요."}


class SubscriptionService:
    """구독 관련 서비스"""

    def __init__(self, subscription: Subs):
        self.subscription = subscription

    def pause_subscription(self) -> Dict[str, Any]:
        """구독 중지 (포트원의 예약 결제도 중지)"""
        try:
            if self.subscription.billing_key:
                billing_key = self.subscription.billing_key.billing_key
                plan_id = self.subscription.plan.id

                # 포트원 예약 결제 조회
                scheduled_payments = fetch_scheduled_payments(billing_key, plan_id)
                if scheduled_payments:
                    logger.info(
                        f"예약된 결제 취소 진행 - 스케줄 ID: {scheduled_payments}"
                    )

                    #  포트원의 예약 결제 취소
                    cancel_scheduled_payments(billing_key, plan_id)

            #  현재 남은 기간 저장
            if self.subscription.end_date:
                remaining_time = self.subscription.end_date - now()
                self.subscription.remaining_bill_date = max(
                    timedelta(seconds=0), remaining_time
                )  # 음수 방지
            else:
                self.subscription.remaining_bill_date = timedelta(seconds=0)

            #  구독 중지 처리
            self.subscription.user.sub_status = "paused"
            self.subscription.end_date = None  # 중지 시 만료일 초기화
            self.subscription.next_bill_date = None  # 중지 시 다음 결제일 초기화
            self.subscription.auto_renew = False  # 자동 갱신 비활성화
            self.subscription.user.save(update_fields=["sub_status"])
            self.subscription.save(
                update_fields=["end_date", "auto_renew", "remaining_bill_date"]
            )

            SubHistories.objects.create(
                sub=self.subscription,
                user=self.subscription.user,
                plan=self.subscription.plan,
                change_date=now(),
                status="pause",
            )

            logger.info(
                f"구독 중지 완료 - 남은 기간 저장: {self.subscription.remaining_bill_date}"
            )

            return {
                "message": "구독이 중지되었습니다.",
                "remaining_days": self.subscription.remaining_bill_date.days,
            }

        except Exception as e:
            logger.error(f"구독 중지 실패: {e}")
            return {"error": "구독 중지 중 오류 발생"}

    def resume_subscription(self) -> Dict[str, Any]:
        """구독 재개 (남은 기간 반영 및 포트원 예약 결제 갱신)"""
        try:
            if self.subscription.user.sub_status != "paused":
                return {"error": "구독이 중지 상태가 아닙니다."}

            # 기존 저장된 남은 기간 확인 (하루씩 줄어드는 문제 해결)
            remaining_time = (
                self.subscription.remaining_bill_date
                if self.subscription.remaining_bill_date
                else timedelta(seconds=0)
            )
            if remaining_time.total_seconds() <= 0:
                return {"error": "남은 기간이 없습니다. 새롭게 구독해야 합니다."}

            start_date = now()  # 구독 재개 시점을 새로운 시작일로 설정
            new_end_date = (
                start_date + remaining_time
            )  # 기존 남은 기간을 유지하여 종료일 설정

            # 구독 상태 변경 및 새로운 종료일 저장
            self.subscription.user.sub_status = "active"
            self.subscription.start_date = start_date  # 구독 재개일 갱신
            self.subscription.end_date = (
                new_end_date  # 기존 남은 기간을 반영한 종료일 설정
            )
            self.subscription.next_bill_date = (
                new_end_date  # 다음 결제일을 종료일로 설정
            )
            self.subscription.auto_renew = True  # 자동 갱신 활성화
            self.subscription.remaining_bill_date = new_end_date - start_date
            self.subscription.user.save(update_fields=["sub_status"])
            self.subscription.save(
                update_fields=["start_date", "end_date", "next_bill_date", "auto_renew"]
            )

            SubHistories.objects.create(
                sub=self.subscription,
                user=self.subscription.user,
                plan=self.subscription.plan,
                change_date=now(),
                status="restarted",
            )

            # 포트원 예약 결제 다시 생성
            if (
                self.subscription.billing_key is None
                or self.subscription.billing_key.billing_key is None
            ):
                raise ValueError("Billing Key가 존재하지 않습니다.")
            billing_key = self.subscription.billing_key.billing_key
            plan_id = self.subscription.plan.id
            plan_price = self.subscription.plan.price

            scheduled_payment_id = create_scheduled_payment(
                billing_key=billing_key,
                plan_id=plan_id,
                price=plan_price,
                user=self.subscription.user,
            )

            logger.info(
                f" 구독 재개 및 포트원 예약 결제 생성 완료: {scheduled_payment_id}"
            )
            return {"message": "구독이 재개되었습니다.", "new_end_date": new_end_date}

        except Exception as e:
            logger.error(f" 구독 재개 실패: {e}")
            return {"error": "구독 재개 중 오류 발생"}

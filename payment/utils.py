import json
import logging
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware, now
from portone_server_sdk._generated.common.billing_key_payment_input import (
    BillingKeyPaymentInput,
)
from portone_server_sdk._generated.common.customer_input import CustomerInput
from portone_server_sdk._generated.common.customer_name_input import CustomerNameInput
from portone_server_sdk._generated.common.payment_amount_input import PaymentAmountInput
from portone_server_sdk._generated.errors import PgProviderError
from portone_server_sdk._generated.payment.payment_schedule.payment_schedule_filter_input import (
    PaymentScheduleFilterInput,
)
from rest_framework import response

from payment import portone_client2
from payment.models import BillingKey
from subscription.models import Subs
from user.models import CustomUser


logger = logging.getLogger(__name__)


def fetch_scheduled_payments(billing_key: str, plan_id: int) -> List[str]:
    """포트원에서 특정 빌링키의 예약된 결제 조회"""

    try:
        KST = timezone(timedelta(hours=9))
        now_kst = datetime.now(KST).replace(microsecond=0).isoformat()
        future_time = (
            (datetime.now(KST) + timedelta(days=370)).replace(microsecond=0).isoformat()
        )

        logger.info(f" 예약 결제 조회 - billing_key: {billing_key}")
        logger.info(f" 조회 기간 - from: {now_kst}, until: {future_time}")

        response = portone_client2.payment_schedule.get_payment_schedules(
            filter=PaymentScheduleFilterInput(
                billing_key=billing_key, from_=now_kst, until=future_time
            )
        )

        # API 응답 확인
        logger.info(f"get_payment_schedules() 응답 전체: {vars(response)}")
        logger.info(
            f"응답 페이지 정보: total_count={response.page.total_count}, number={response.page.number}, size={response.page.size}"
        )

        # 예약된 결제 리스트 추출
        scheduled_payments: List[str] = []
        for schedule in response.items:
            try:
                # revoked_at 필드가 존재하고 값이 있으면 취소된 결제 → 제외
                if hasattr(schedule, "revoked_at") and schedule.revoked_at:
                    logger.info(f" 이미 취소된 결제 - 스케줄 ID: {schedule.id}, 취소 시각: {schedule.revoked_at}")  # type: ignore
                    continue  # 취소된 결제는 리스트에 추가하지 않음

                #  custom_data 존재 여부 확인
                custom_data = getattr(schedule, "custom_data", None)

                #  custom_data가 없거나 비어 있으면 `order_name` 기반으로 필터링
                if not custom_data or custom_data.strip() == "":
                    logger.warning(f"custom_data가 비어 있음: {custom_data}")

                    if hasattr(schedule, "order_name") and schedule.order_name:
                        logger.info(f"기본 필터링 사용 - 스케줄 ID: {schedule.id}, order_name: {schedule.order_name}")  # type: ignore
                        scheduled_payments.append(schedule.id)  # type: ignore
                    continue

                # custom_data가 JSON인지 확인 후 변환
                try:
                    custom_data = json.loads(custom_data)
                except json.JSONDecodeError:
                    logger.warning(f" JSON 변환 실패: {custom_data}")
                    continue

                # custom_data가 딕셔너리인지 확인 후 `plan_id` 비교
                if (
                    isinstance(custom_data, dict)
                    and custom_data.get("plan_id") == plan_id
                ):
                    logger.info(f"plan_id 일치 - 스케줄 ID: {schedule.id}")  # type: ignore
                    scheduled_payments.append(schedule.id)  # type: ignore

            except AttributeError as e:
                logger.warning(f"데이터 필터링 중 오류 발생: {e}")

        logger.info(f"최종 예약된 결제 스케줄 ID 리스트: {scheduled_payments}")
        return scheduled_payments

    except Exception as e:
        logger.warning(f"예약 결제 조회 실패: {e}")
        return []


def delete_billing_key_with_retry(
    billing_key: str, reason: str = "사용자 요청으로 인한 자동 결제 해지"
) -> bool:
    """포트원 서버에 빌링키 삭제 요청 및 상태 확인 후 안전하게 처리"""
    try:
        # 삭제 요청 실행
        response = portone_client2.billing_key.delete_billing_key(
            billing_key=billing_key, reason=reason
        )
        logger.info(f"Billing_Key 삭제 요청 성공: {response}")

        # 삭제 후 포트원 서버에서 상태 확인
        billing_status = check_billing_key_status(billing_key)

        if billing_status is None:
            logger.info(f" 포트원 서버에서 빌링 키 삭제 확인 완료: {billing_key}")
            return True
        else:
            logger.warning(f"포트원 서버에서 빌링 키가 여전히 존재함: {billing_key}")
            return False

    except PgProviderError as e:
        if "P759" in str(e):
            logger.warning(f"P759 발생 - 빌링 키가 이미 삭제됨: {billing_key}")
            return True  # 이미 삭제된 것으로 간주
        logger.error(f"빌링 키 삭제 중 오류 발생: {e}")
        return False

    except Exception as e:
        logger.error(f" 예상치 못한 오류 발생: {e}")
        return False


def check_billing_key_status(billing_key: str) -> Optional[Any]:
    """포트원 서버에서 빌링키 상태 확인"""
    try:
        response = portone_client2.billing_key.get_billing_key_info(
            billing_key=billing_key
        )
        logger.info(f" 빌링키 상태 조회 결과: {response}")
        return response
    except PgProviderError as e:
        logger.warning(f" P759 발생 - 빌링 키가 이미 삭제되었을 가능성 있음: {e}")
        return None


def cancel_scheduled_payments(billing_key: str, plan_id: int) -> bool:
    """포트원의 예약된 결제 취소"""
    try:
        scheduled_payments = fetch_scheduled_payments(billing_key, plan_id)

        if scheduled_payments:
            logger.info(
                f"정기 결제 스케줄 발견 (취소 대상 플랜 ID: {plan_id}): {scheduled_payments}, 스케줄 취소 진행."
            )

            # 해당하는 스케줄만 취소
            portone_client2.payment_schedule.revoke_payment_schedules(
                billing_key=billing_key, schedule_ids=scheduled_payments
            )
            logger.info(f"특정 플랜 ({plan_id})에 대한 정기 결제 스케줄 취소 완료.")
            return True
        return False

    except Exception as e:
        logger.error(f"포트원 예약 결제 취소 실패: {e}")
        return False


def create_scheduled_payment(
    billing_key: str, plan_id: int, price: int, user: CustomUser
) -> str:
    """포트원의 예약 결제 생성 (구독 재개 시)"""

    # 구독 정보 가져오기 (특정 플랜 기준으로 조회)
    subscription = user.subs_set.filter(plan_id=plan_id).first()
    if not subscription:
        raise ValueError("해당 유저의 구독 정보를 찾을 수 없습니다.")

    start_date = now()  # 구독 재개일을 새로운 구독 시작일로 설정
    remaining_days = (
        subscription.remaining_bill_date.days if subscription.remaining_bill_date else 0
    )

    if remaining_days <= 0:
        raise ValueError("남은 구독 기간이 없습니다. 새로 구독해야 합니다.")

    end_date = start_date + timedelta(days=remaining_days)
    next_billing_date = end_date  # 다음 결제일을 종료일로 설정

    scheduled_payment_id = f"SUBS{uuid.uuid4().hex[:18]}"

    customer_info = CustomerInput(
        id=str(user.id),
        email=user.email or "",
        name=CustomerNameInput(full=user.name or "Unnamed User"),
    )

    try:
        schedule_response = portone_client2.payment_schedule.create_payment_schedule(
            payment_id=scheduled_payment_id,
            payment=BillingKeyPaymentInput(
                billing_key=billing_key.strip(),
                order_name=f"Plan-{plan_id}",
                amount=PaymentAmountInput(total=int(price)),
                currency="KRW",
                customer=customer_info,
            ),
            time_to_pay=next_billing_date.isoformat(),
        )

        logger.info(f"포트원 예약 결제 응답: {schedule_response}")

        # schedule_id를 올바른 방식으로 가져오기
        if hasattr(schedule_response, "schedule") and hasattr(
            schedule_response.schedule, "id"
        ):
            scheduled_id = schedule_response.schedule.id
            logger.info(f" 포트원 예약 결제 생성 완료 - 스케줄 ID: {scheduled_id}")
        else:
            logger.warning(f" 포트원 응답에 schedule_id 없음: {schedule_response}")
            scheduled_id = ""

        return scheduled_id

    except Exception as e:
        logger.error(f" 포트원 예약 결제 생성 실패: {e}")
        return ""


def schedule_new_payment(
    user: CustomUser,
    old_billing_key: str,
    new_billing_key: str,
    plan_id: int,
    amount: int,
) -> str:
    """가장 최근 취소된 결제 정보를 유지하며 새로운 Billing Key로 결제 예약"""
    try:
        logger.info(
            f" 새로운 Billing Key로 정기 결제 예약: {new_billing_key} (사용자: {user.id})"
        )

        #  포트원에서 기존 예약된 결제 조회 (취소된 결제 포함)
        payment_schedules = fetch_scheduled_cancelled_payments(old_billing_key, plan_id)

        #  가장 최근 취소된 결제를 찾기 (최신순 정렬 후 첫 번째 선택)
        cancelled_schedules = sorted(
            [s for s in payment_schedules if s.get("revoked_at")],
            key=lambda x: x["revoked_at"],
            reverse=True,
        )

        if not cancelled_schedules:
            logger.error("취소된 결제 내역이 없어 새로운 결제 예약을 할 수 없습니다.")
            return ""  # 취소된 결제가 없으면 새 예약을 하지 않음

        # 가장 최근 취소된 결제 정보 가져오기
        recent_cancelled = cancelled_schedules[0]
        time_to_pay = recent_cancelled.get("time_to_pay")
        created_at = recent_cancelled.get("created_at")
        total_amount = recent_cancelled.get("total_amount")
        order_name = recent_cancelled.get("order_name")

        if not time_to_pay or not created_at:
            logger.error(
                f"취소된 결제 정보가 올바르지 않습니다. time_to_pay={time_to_pay}, created_at={created_at}"
            )
            return ""

        logger.warning(
            f"⚠ 기존 Billing Key가 취소됨 - 스케줄 ID: {recent_cancelled['id']}, "
            f"취소된 결제일 적용: {time_to_pay}, 등록일: {created_at}"
        )

        # 기존 결제 일정 유지 (새로운 결제일 생성 X)
        parsed_time_to_pay = parse_datetime(time_to_pay) if time_to_pay else None
        parsed_created_at = parse_datetime(created_at) if created_at else None

        if parsed_time_to_pay is None or parsed_created_at is None:
            logger.error(" 결제 일정 변환 중 오류 발생")
            return ""

        # 타임존 확인 후 적용
        new_schedule_date = (
            make_aware(parsed_time_to_pay)
            if is_naive(parsed_time_to_pay)
            else parsed_time_to_pay
        )
        created_at_dt = (
            make_aware(parsed_created_at)
            if is_naive(parsed_created_at)
            else parsed_created_at
        )

        logger.info(f" 최종 적용 결제일: {new_schedule_date}, 등록일: {created_at_dt}")

        #  새 결제 ID 생성
        scheduled_payment_id = f"SUBS{uuid.uuid4().hex[:18]}"

        # 고객 정보 입력
        customer_info = CustomerInput(
            id=str(user.id),
            email=user.email or "",
            name=CustomerNameInput(full=user.name or "Unnamed User"),
        )

        # 새로운 Billing Key로 결제 예약 (기존 결제 일정 유지)
        schedule_response = portone_client2.payment_schedule.create_payment_schedule(
            payment_id=scheduled_payment_id,
            payment=BillingKeyPaymentInput(
                billing_key=new_billing_key.strip(),
                order_name=order_name,  # type: ignore
                amount=PaymentAmountInput(total=int(total_amount)),  # type: ignore
                currency="KRW",
                customer=customer_info,
            ),
            time_to_pay=new_schedule_date.isoformat(),  # 기존 결제일 적용
        )

        # 포트원 응답 확인
        if hasattr(schedule_response, "schedule") and hasattr(
            schedule_response.schedule, "id"
        ):
            scheduled_id = schedule_response.schedule.id
            logger.info(f"포트원 예약 결제 생성 완료 - 스케줄 ID: {scheduled_id}")
        else:
            logger.warning(f"포트원 응답에 schedule_id 없음: {schedule_response}")
            scheduled_id = ""

        return scheduled_id

    except Exception as e:
        logger.error(f"새 Billing Key로 결제 예약 실패: {e}")
        return ""


def fetch_scheduled_cancelled_payments(
    billing_key: str, plan_id: int
) -> List[Dict[str, str]]:
    """포트원에서 특정 빌링키의 예약된 결제 조회 (취소된 결제 포함)"""

    try:
        KST = timezone(timedelta(hours=9))
        now_kst = datetime.now(KST).replace(microsecond=0).isoformat()
        future_time = (
            (datetime.now(KST) + timedelta(days=370)).replace(microsecond=0).isoformat()
        )

        logger.info(f" 예약 결제 조회 - billing_key: {billing_key}")
        logger.info(f" 조회 기간 - from: {now_kst}, until: {future_time}")

        response = portone_client2.payment_schedule.get_payment_schedules(
            filter=PaymentScheduleFilterInput(
                billing_key=billing_key, from_=now_kst, until=future_time
            )
        )

        # API 응답 확인
        logger.info(f"get_payment_schedules() 응답 전체: {vars(response)}")
        logger.info(
            f"응답 페이지 정보: total_count={response.page.total_count}, number={response.page.number}, size={response.page.size}"
        )

        # 예약된 결제 리스트 추출
        scheduled_payments: List[Dict[str, str]] = []
        for schedule in response.items:
            try:
                payment_info = {
                    "id": schedule.id,  # type: ignore
                    "revoked_at": getattr(
                        schedule, "revoked_at", None
                    ),  # 취소된 경우 해당 필드 포함
                    "time_to_pay": getattr(
                        schedule, "time_to_pay", None
                    ),  # 결제 예정일
                    "created_at": getattr(schedule, "created_at", None),
                    "order_name": getattr(schedule, "order_name", None),
                    "total_amount": getattr(schedule, "total_amount", None),
                }

                if payment_info["revoked_at"]:
                    logger.info(
                        f" 취소된 결제 포함 - 스케줄 ID: {payment_info['id']}, "
                        f"취소 시각: {payment_info['revoked_at']}, 등록일: {payment_info['created_at']}"
                    )
                else:
                    logger.info(
                        f"정상 예약 결제 - 스케줄 ID: {payment_info['id']}, "
                        f"결제 예정일: {payment_info['time_to_pay']}, 등록일: {payment_info['created_at']}"
                    )

                # 모든 결제 (취소된 것 포함) 리스트에 추가
                scheduled_payments.append(payment_info)  # type: ignore

            except AttributeError as e:
                logger.warning(f"데이터 필터링 중 오류 발생: {e}")

        logger.info(f"최종 예약된 결제 리스트: {scheduled_payments}")
        return scheduled_payments

    except Exception as e:
        logger.warning(f"예약 결제 조회 실패: {e}")
        return []


def update_billing_key_info(billing_key_obj: BillingKey, new_billing_key: str) -> None:
    """Billing Key 카드 정보 업데이트"""
    billing_key_obj.billing_key = new_billing_key

    # Billing Key 정보 조회
    billing_key_info = portone_client2.billing_key.get_billing_key_info(
        billing_key=new_billing_key
    )

    # methods(결제 카드 정보) 값 추출
    if isinstance(billing_key_info, dict):
        methods = billing_key_info.get("methods", [])
    elif hasattr(billing_key_info, "methods"):
        methods = billing_key_info.methods
    else:
        methods = []

    # issuer(card name)  number 값 추출
    if methods:
        first_method = methods[0]  # 첫 번째 카드 정보 사용
        billing_key_obj.card_name = (
            first_method.card.issuer if first_method.card.issuer else "Unknown Card"
        )
        billing_key_obj.card_number = first_method.card.number
    else:
        billing_key_obj.card_name = None
        billing_key_obj.card_number = None

    billing_key_obj.save(update_fields=["billing_key", "card_name", "card_number"])
    logger.info(
        f"[UpdateBillingKey] 카드 정보 업데이트 완료: {billing_key_obj.card_name}, {billing_key_obj.card_number}"
    )

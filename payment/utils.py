import json
import logging

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from portone_server_sdk._generated.errors import PgProviderError
from portone_server_sdk._generated.payment.payment_schedule.payment_schedule_filter_input import (
    PaymentScheduleFilterInput,
)

from payment import portone_client2


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
            logger.warning(f"⚠P759 발생 - 빌링 키가 이미 삭제됨: {billing_key}")
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

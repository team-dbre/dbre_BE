from typing import Generator

import pytest

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from dbre_BE.scheduler import start


@pytest.fixture(scope="module")
def scheduler() -> Generator[BackgroundScheduler, None, None]:
    scheduler = start()  # start() 함수가 스케줄러를 반환하도록 수정
    yield scheduler
    scheduler.shutdown(wait=False)


def test_scheduler_jobs(scheduler: BackgroundScheduler) -> None:
    # 스케줄러에 등록된 모든 작업 가져오기
    jobs = scheduler.get_jobs()

    # 등록된 작업 수 확인
    assert len(jobs) == 2

    # 각 작업의 ID와 트리거 타입 확인
    job_ids = [job.id for job in jobs]
    assert "delete_inactive_users" in job_ids
    assert "process_scheduled_payments" in job_ids

    # 각 작업의 트리거 타입 확인
    for job in jobs:
        if job.id == "delete_inactive_users":
            assert job.trigger.__class__.__name__ == "CronTrigger"
        elif job.id == "process_scheduled_payments":
            assert job.trigger.__class__.__name__ == "IntervalTrigger"


def test_delete_inactive_users_schedule(scheduler: BackgroundScheduler) -> None:
    job = scheduler.get_job("delete_inactive_users")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)

    # CronTrigger의 필드를 직접 확인
    hour_field = next((f for f in job.trigger.fields if f.name == "hour"), None)
    assert hour_field is not None
    assert len(hour_field.expressions) == 1
    assert hour_field.expressions[0].first == 5  # RangeExpression의 first 속성 확인

    minute_field = next((f for f in job.trigger.fields if f.name == "minute"), None)
    assert minute_field is not None
    assert len(minute_field.expressions) == 1
    assert minute_field.expressions[0].first == 0


def test_process_scheduled_payments_schedule(scheduler: BackgroundScheduler) -> None:
    job = scheduler.get_job("process_scheduled_payments")
    assert job is not None
    assert job.trigger.interval.days == 1

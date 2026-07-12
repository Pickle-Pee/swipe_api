from datetime import datetime, timedelta

import pytest

from common.models import Subscription, User, UserSubscription
from common.utils.scheduler import (
    RecurrentBillingDisabledError,
    auto_renew_subscriptions,
    deactivate_expired_subscriptions,
    start_scheduler,
)
from config import SessionLocal


def test_expiration_maintenance_is_idempotent_and_keeps_active_access(
    isolated_database,
):
    now = datetime.utcnow()
    with SessionLocal() as db:
        user = db.query(User).first()
        plan = db.query(Subscription).filter(Subscription.price_minor > 0).first()
        expired = UserSubscription(
            user_id=user.id,
            subscription_id=plan.id,
            start_date=now - timedelta(days=31),
            end_date=now - timedelta(days=1),
            is_active=True,
            renewable=True,
            next_billing_date=now - timedelta(days=1),
        )
        active = UserSubscription(
            user_id=user.id,
            subscription_id=plan.id,
            start_date=now,
            end_date=now + timedelta(days=30),
            is_active=True,
            renewable=True,
            next_billing_date=now + timedelta(days=30),
        )
        db.add_all([expired, active])
        db.commit()
        expired_id, active_id = expired.id, active.id
        active_end = active.end_date

    assert deactivate_expired_subscriptions(now) == 1
    assert deactivate_expired_subscriptions(now) == 0

    with SessionLocal() as db:
        expired = db.get(UserSubscription, expired_id)
        active = db.get(UserSubscription, active_id)
        assert expired.is_active is False
        assert expired.renewable is False
        assert expired.next_billing_date is None
        assert active.is_active is True
        assert active.renewable is True
        assert active.end_date == active_end
        db.delete(expired)
        db.delete(active)
        db.commit()


def test_manual_legacy_renewal_never_calls_http_or_changes_database(
    isolated_database, monkeypatch
):
    def fail_http(*args, **kwargs):
        raise AssertionError("legacy renewal attempted an external HTTP request")

    monkeypatch.setattr("requests.sessions.Session.request", fail_http)
    with SessionLocal() as db:
        before = [
            (item.id, item.end_date, item.is_active, item.renewable)
            for item in db.query(UserSubscription).order_by(UserSubscription.id)
        ]

    with pytest.raises(RecurrentBillingDisabledError, match="disabled"):
        auto_renew_subscriptions()

    with SessionLocal() as db:
        after = [
            (item.id, item.end_date, item.is_active, item.renewable)
            for item in db.query(UserSubscription).order_by(UserSubscription.id)
        ]
    assert after == before


def test_scheduler_registers_only_expiration_maintenance(monkeypatch):
    jobs = []

    class FakeScheduler:
        def __init__(self, **kwargs):
            self.started = False

        def add_job(self, function, *args, **kwargs):
            jobs.append((function, args, kwargs))

        def start(self):
            self.started = True

    monkeypatch.setattr("common.utils.scheduler.IS_DEMO", False)
    monkeypatch.setattr("common.utils.scheduler.BackgroundScheduler", FakeScheduler)
    scheduler = start_scheduler()

    assert scheduler.started is True
    assert [job[0] for job in jobs] == [deactivate_expired_subscriptions]
    assert jobs[0][2]["id"] == "deactivate_expired_subscriptions"


def test_demo_does_not_start_any_scheduler(monkeypatch):
    def fail_scheduler(*args, **kwargs):
        raise AssertionError("demo attempted to create a scheduler")

    monkeypatch.setattr("common.utils.scheduler.IS_DEMO", True)
    monkeypatch.setattr("common.utils.scheduler.BackgroundScheduler", fail_scheduler)
    assert start_scheduler() is None

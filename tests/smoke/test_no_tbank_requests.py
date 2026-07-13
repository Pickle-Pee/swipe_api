from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest

from common.models import City, Subscription, Transaction, User, UserSubscription
from common.services import generate_tbank_token
from common.services.tbank_client import TBankClient, TBankClientError, TBankInitRequest
from common.utils.scheduler import (
    RecurrentBillingDisabledError,
    auto_renew_subscriptions,
    deactivate_expired_subscriptions,
    start_scheduler,
)
from config import SessionLocal


TERMINAL = "security-test-terminal"
PASSWORD = "security-test-password"


@pytest.fixture(autouse=True)
def deny_external_http(monkeypatch):
    """Fail immediately if any scenario reaches requests' real transport."""

    def denied(*args, **kwargs):
        raise AssertionError("unexpected external HTTP request")

    monkeypatch.setattr("requests.sessions.Session.request", denied)
    monkeypatch.setattr("requests.api.request", denied)


def _register(client, phone: str) -> dict[str, str]:
    with SessionLocal() as db:
        city_name = db.query(City.city_name).first()[0]
    assert (
        client.post("/auth/send_code", params={"phone_number": phone}).status_code
        == 200
    )
    response = client.post(
        "/auth/register",
        json={
            "phone_number": phone,
            "first_name": "NoBank",
            "last_name": "Security",
            "date_of_birth": "1995-01-01",
            "gender": "female",
            "city_name": city_name,
        },
    )
    assert response.status_code in {200, 201}, response.text
    token = response.json()["access_token"]
    return {
        "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}"
    }


def _plan(client, headers):
    response = client.get("/subscriptions", headers=headers)
    assert response.status_code == 200, response.text
    return next(
        item for item in response.json()["subscriptions"] if item["price_minor"] > 0
    )


def _checkout(client, headers, key):
    plan = _plan(client, headers)
    response = client.post(
        "/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": key},
        json={"subscription_id": plan["id"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _configure_webhook(monkeypatch):
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_KEY", TERMINAL
    )
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_PASSWORD", PASSWORD
    )


def _confirmed(checkout):
    payload = {
        "TerminalKey": TERMINAL,
        "OrderId": checkout["order_id"],
        "PaymentId": checkout["payment_id"],
        "Status": "CONFIRMED",
        "Amount": checkout["amount_minor"],
        "Success": True,
        "ErrorCode": "0",
    }
    payload["Token"] = generate_tbank_token(payload, PASSWORD)
    return payload


def test_demo_startup_imports_and_recurrent_guard_never_reach_http(client, monkeypatch):
    import app
    import common.services.tbank_client
    import common.utils.scheduler
    import controllers.subscription_controller

    assert importlib.import_module("app") is app
    assert (
        importlib.import_module("common.services.tbank_client")
        is common.services.tbank_client
    )
    assert importlib.import_module("common.utils.scheduler") is common.utils.scheduler
    assert (
        importlib.import_module("controllers.subscription_controller")
        is controllers.subscription_controller
    )

    monkeypatch.setattr("common.utils.scheduler.IS_DEMO", True)
    assert start_scheduler() is None
    with pytest.raises(RecurrentBillingDisabledError, match="disabled"):
        auto_renew_subscriptions()


def test_expiration_catalog_active_and_cancel_never_reach_http(client):
    headers = _register(client, "70000000681")
    assert client.get("/subscriptions", headers=headers).status_code == 200
    assert client.get("/subscriptions/active", headers=headers).json() == {
        "subscription": None
    }

    now = datetime.utcnow()
    with SessionLocal() as db:
        user = db.query(User).filter(User.phone_number == "70000000681").one()
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
        expired_id = expired.id

    assert deactivate_expired_subscriptions(now) == 1
    assert client.get("/subscriptions/active", headers=headers).status_code == 200
    canceled = client.post("/subscriptions/cancel", headers=headers)
    assert canceled.status_code == 200
    assert canceled.json()["subscription"]["renewable"] is False
    with SessionLocal() as db:
        assert db.get(UserSubscription, expired_id).is_active is False


def test_legacy_and_pre_init_validation_never_reach_http(client):
    headers = _register(client, "70000000682")
    legacy = client.post(
        "/subscriptions/init_payment",
        json={"amount": 1, "price": 1, "subscriptionId": 1},
    )
    assert legacy.status_code == 410

    missing_key = client.post(
        "/subscriptions/checkout", headers=headers, json={"subscription_id": 1}
    )
    assert missing_key.status_code == 422
    extra_price = client.post(
        "/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "security-no-bank-01"},
        json={"subscription_id": 1, "amount": 1, "price": 1},
    )
    assert extra_price.status_code == 422


def test_unknown_and_inactive_plans_never_reach_http(client):
    headers = _register(client, "70000000683")
    unknown = client.post(
        "/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "security-no-bank-02"},
        json={"subscription_id": 999999},
    )
    assert unknown.status_code == 404

    with SessionLocal() as db:
        plan = db.query(Subscription).filter(Subscription.price_minor > 0).first()
        plan.is_active = False
        plan_id = plan.id
        db.commit()
    try:
        inactive = client.post(
            "/subscriptions/checkout",
            headers={**headers, "Idempotency-Key": "security-no-bank-03"},
            json={"subscription_id": plan_id},
        )
        assert inactive.status_code == 409
    finally:
        with SessionLocal() as db:
            db.query(Subscription).filter_by(id=plan_id).update({"is_active": True})
            db.commit()


def test_invalid_and_duplicate_webhooks_never_reach_http(client, monkeypatch):
    invalid = client.post("/subscriptions/webhooks/tbank", json={"Token": "invalid"})
    assert invalid.status_code == 400

    _configure_webhook(monkeypatch)
    headers = _register(client, "70000000684")
    checkout = _checkout(client, headers, "security-no-bank-04")
    confirmed = _confirmed(checkout)
    first = client.post("/subscriptions/webhooks/tbank", json=confirmed)
    second = client.post("/subscriptions/webhooks/tbank", json=confirmed)
    assert first.status_code == 200 and first.text == "OK"
    assert second.status_code == 200 and second.text == "OK"
    with SessionLocal() as db:
        transaction = (
            db.query(Transaction).filter_by(order_id=checkout["order_id"]).one()
        )
        assert transaction.subscription_activated_at is not None
        assert (
            db.query(UserSubscription)
            .filter_by(
                user_id=transaction.user_id,
                subscription_id=transaction.subscription_id,
                is_active=True,
            )
            .count()
            == 1
        )


def test_missing_bank_secrets_fail_before_transport_and_keep_database_unchanged():
    class DeniedSession:
        def post(self, *args, **kwargs):
            raise AssertionError("missing-secret client reached HTTP")

    tbank = TBankClient(
        base_url="https://bank.invalid/v2",
        terminal_key=None,
        password=None,
        recurrent_enabled=False,
        session=DeniedSession(),
    )
    with SessionLocal() as db:
        before = db.query(Transaction).count()

    with pytest.raises(TBankClientError) as error:
        tbank.init_payment(TBankInitRequest(49900, "order", "Plan", "42"))

    assert error.value.code == "provider_not_configured"
    assert "secret" not in str(error.value).lower()
    with SessionLocal() as db:
        assert db.query(Transaction).count() == before

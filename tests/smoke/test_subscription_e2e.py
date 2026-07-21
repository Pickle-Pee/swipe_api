from datetime import UTC, datetime

from common.models import Transaction, UserSubscription
from common.services import generate_tbank_token
from config import SessionLocal


TERMINAL = "e2e-test-terminal"
PASSWORD = "e2e-test-password"


def _register(client):
    phone = "70000000991"
    assert client.post("/auth/send_code", params={"phone_number": phone}).status_code == 200
    response = client.post(
        "/auth/register",
        json={
            "phone_number": phone,
            "first_name": "Subscription",
            "last_name": "E2E",
            "date_of_birth": "1995-01-01",
            "gender": "female",
            "city_name": "Демо-Сити (Демо-регион Север)",
        },
    )
    assert response.status_code in {200, 201}, response.text
    token = response.json()["access_token"]
    return {"Authorization": token if token.startswith("Bearer ") else f"Bearer {token}"}


def _notification(checkout):
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


def test_complete_subscription_flow_is_idempotent_and_cancel_keeps_access(
    client, monkeypatch
):
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_KEY", TERMINAL
    )
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_PASSWORD", PASSWORD
    )
    headers = _register(client)

    plans = client.get("/subscriptions", headers=headers)
    assert plans.status_code == 200, plans.text
    plan = next(item for item in plans.json()["subscriptions"] if item["price_minor"] > 0)

    checkout = client.post(
        "/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": "subscription-e2e-checkout-01"},
        json={"subscription_id": plan["id"]},
    )
    assert checkout.status_code == 201, checkout.text
    checkout_body = checkout.json()

    with SessionLocal() as session:
        transaction = session.query(Transaction).filter_by(
            order_id=checkout_body["order_id"]
        ).one()
        assert transaction.user_id is not None
        assert transaction.subscription_id == plan["id"]
        assert transaction.amount_minor == plan["price_minor"]
        assert transaction.subscription_activated_at is None

    notification = _notification(checkout_body)
    first = client.post("/subscriptions/webhooks/tbank", json=notification)
    assert first.status_code == 200 and first.text == "OK"

    status = client.get(
        f"/subscriptions/payments/{checkout_body['order_id']}", headers=headers
    )
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "succeeded"
    assert status.json()["subscription_activated"] is True

    active = client.get("/subscriptions/active", headers=headers)
    assert active.status_code == 200, active.text
    first_end = active.json()["subscription"]["end_at"]
    assert active.json()["subscription"]["subscription_id"] == plan["id"]

    repeated = client.post("/subscriptions/webhooks/tbank", json=notification)
    assert repeated.status_code == 200 and repeated.text == "OK"
    assert (
        client.get("/subscriptions/active", headers=headers).json()["subscription"]["end_at"]
        == first_end
    )

    with SessionLocal() as session:
        transaction = session.query(Transaction).filter_by(
            order_id=checkout_body["order_id"]
        ).one()
        subscriptions = session.query(UserSubscription).filter_by(
            user_id=transaction.user_id,
            subscription_id=transaction.subscription_id,
        ).all()
        assert len(subscriptions) == 1
        subscriptions[0].renewable = True
        subscriptions[0].next_billing_date = subscriptions[0].end_date
        session.commit()

    canceled = client.post("/subscriptions/cancel", headers=headers)
    assert canceled.status_code == 200, canceled.text
    canceled_subscription = canceled.json()["subscription"]
    assert canceled_subscription["renewable"] is False
    assert canceled_subscription["end_at"] == first_end
    end_at = datetime.fromisoformat(canceled_subscription["end_at"]).replace(tzinfo=UTC)
    assert end_at > datetime.now(UTC)

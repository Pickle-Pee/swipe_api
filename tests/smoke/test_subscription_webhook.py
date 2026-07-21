from datetime import datetime

from common.models import Transaction, UserSubscription
from common.services import generate_tbank_token
from config import SessionLocal


TERMINAL = "test-terminal"
PASSWORD = "test-password"


def _register(client, phone):
    assert (
        client.post("/auth/send_code", params={"phone_number": phone}).status_code
        == 200
    )
    response = client.post(
        "/auth/register",
        json={
            "phone_number": phone,
            "first_name": "Webhook",
            "last_name": "Tester",
            "date_of_birth": "1995-01-01",
            "gender": "female",
            "city_name": "Демо-Сити (Демо-регион Север)",
        },
    )
    assert response.status_code in {200, 201}, response.text
    token = response.json()["access_token"]
    return {
        "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}"
    }


def _checkout(client, headers, key):
    plan = next(
        item
        for item in client.get("/subscriptions", headers=headers).json()[
            "subscriptions"
        ]
        if item["price_minor"] > 0
    )
    response = client.post(
        "/subscriptions/checkout",
        headers={**headers, "Idempotency-Key": key},
        json={"subscription_id": plan["id"]},
    )
    assert response.status_code == 201, response.text
    return response.json(), plan


def _payload(checkout, status, **extra):
    payload = {
        "TerminalKey": TERMINAL,
        "OrderId": checkout["order_id"],
        "PaymentId": checkout["payment_id"],
        "Status": status,
        "Amount": checkout["amount_minor"],
        "Success": status in {"AUTHORIZED", "CONFIRMED"},
        "ErrorCode": "0",
        **extra,
    }
    payload["Token"] = generate_tbank_token(payload, PASSWORD)
    return payload


def _configure_webhook(monkeypatch):
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_KEY", TERMINAL
    )
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_PASSWORD", PASSWORD
    )


def test_authorized_saves_rebill_confirmed_activates_once_and_stale_is_ignored(
    client, monkeypatch
):
    _configure_webhook(monkeypatch)
    headers = _register(client, "70000000771")
    checkout, plan = _checkout(client, headers, "webhook-checkout-key-01")

    authorized = _payload(
        checkout, "AUTHORIZED", RebillId="rebill-test", CardId="card-test"
    )
    response = client.post("/subscriptions/webhooks/tbank", json=authorized)
    assert response.status_code == 200 and response.text == "OK"
    assert (
        client.get(
            f"/subscriptions/payments/{checkout['order_id']}", headers=headers
        ).json()["status"]
        == "processing"
    )
    with SessionLocal() as session:
        transaction = (
            session.query(Transaction).filter_by(order_id=checkout["order_id"]).one()
        )
        assert transaction.rebill_id == "rebill-test"
        assert transaction.subscription_activated_at is None

    confirmed = _payload(checkout, "CONFIRMED", RebillId="rebill-test")
    assert client.post("/subscriptions/webhooks/tbank", json=confirmed).text == "OK"
    active = client.get("/subscriptions/active", headers=headers)
    assert active.status_code == 200
    assert active.json()["subscription"]["subscription_id"] == plan["id"]
    first_end = active.json()["subscription"]["end_at"]

    assert client.post("/subscriptions/webhooks/tbank", json=confirmed).text == "OK"
    stale = _payload(checkout, "NEW")
    assert client.post("/subscriptions/webhooks/tbank", json=stale).text == "OK"
    assert (
        client.get("/subscriptions/active", headers=headers).json()["subscription"][
            "end_at"
        ]
        == first_end
    )
    status = client.get(
        f"/subscriptions/payments/{checkout['order_id']}", headers=headers
    ).json()
    assert status["status"] == "succeeded"
    assert status["subscription_activated"] is True
    refunded = _payload(checkout, "REFUNDED")
    assert client.post("/subscriptions/webhooks/tbank", json=refunded).text == "OK"
    refunded_status = client.get(
        f"/subscriptions/payments/{checkout['order_id']}", headers=headers
    ).json()
    assert refunded_status["status"] == "refunded"


def test_second_confirmed_payment_extends_active_subscription_once(client, monkeypatch):
    _configure_webhook(monkeypatch)
    headers = _register(client, "70000000772")
    first, _ = _checkout(client, headers, "webhook-checkout-key-02")
    assert (
        client.post(
            "/subscriptions/webhooks/tbank", json=_payload(first, "CONFIRMED")
        ).text
        == "OK"
    )
    first_end = datetime.fromisoformat(
        client.get("/subscriptions/active", headers=headers).json()["subscription"][
            "end_at"
        ]
    )

    second, plan = _checkout(client, headers, "webhook-checkout-key-03")
    confirmed = _payload(second, "CONFIRMED")
    assert client.post("/subscriptions/webhooks/tbank", json=confirmed).text == "OK"
    second_end = datetime.fromisoformat(
        client.get("/subscriptions/active", headers=headers).json()["subscription"][
            "end_at"
        ]
    )
    assert (second_end - first_end).days == plan["duration_days"]
    assert client.post("/subscriptions/webhooks/tbank", json=confirmed).text == "OK"
    repeated_end = datetime.fromisoformat(
        client.get("/subscriptions/active", headers=headers).json()["subscription"][
            "end_at"
        ]
    )
    assert repeated_end == second_end


def test_webhook_rejects_invalid_signature_terminal_ids_and_amount(client, monkeypatch):
    _configure_webhook(monkeypatch)
    headers = _register(client, "70000000773")
    checkout, _ = _checkout(client, headers, "webhook-checkout-key-04")

    invalid = _payload(checkout, "CONFIRMED")
    invalid["Token"] = "invalid"
    assert client.post("/subscriptions/webhooks/tbank", json=invalid).status_code == 403

    wrong_terminal = _payload(checkout, "CONFIRMED")
    wrong_terminal["TerminalKey"] = "other"
    wrong_terminal["Token"] = generate_tbank_token(wrong_terminal, PASSWORD)
    assert (
        client.post("/subscriptions/webhooks/tbank", json=wrong_terminal).status_code
        == 403
    )

    for field, value, expected in (
        ("OrderId", "other-order", 400),
        ("Amount", checkout["amount_minor"] + 1, 400),
        ("PaymentId", "unknown-payment", 404),
    ):
        payload = _payload(checkout, "CONFIRMED")
        payload[field] = value
        payload["Token"] = generate_tbank_token(payload, PASSWORD)
        assert (
            client.post("/subscriptions/webhooks/tbank", json=payload).status_code
            == expected
        )


def test_failed_does_not_activate_and_cancel_keeps_paid_period(client, monkeypatch):
    _configure_webhook(monkeypatch)
    headers = _register(client, "70000000774")
    failed, _ = _checkout(client, headers, "webhook-checkout-key-05")
    rejected = _payload(failed, "REJECTED", ErrorCode="1006")
    assert client.post("/subscriptions/webhooks/tbank", json=rejected).text == "OK"
    assert client.get("/subscriptions/active", headers=headers).json() == {
        "subscription": None
    }

    paid, _ = _checkout(client, headers, "webhook-checkout-key-06")
    assert (
        client.post(
            "/subscriptions/webhooks/tbank", json=_payload(paid, "CONFIRMED")
        ).text
        == "OK"
    )
    with SessionLocal() as session:
        transaction = (
            session.query(Transaction).filter_by(order_id=paid["order_id"]).one()
        )
        active = (
            session.query(UserSubscription)
            .filter_by(
                user_id=transaction.user_id,
                subscription_id=transaction.subscription_id,
            )
            .one()
        )
        active.renewable = True
        active.next_billing_date = active.end_date
        end_date = active.end_date
        session.commit()
    canceled = client.post("/subscriptions/cancel", headers=headers)
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["subscription"]["renewable"] is False
    assert datetime.fromisoformat(canceled.json()["subscription"]["end_at"]) == end_date

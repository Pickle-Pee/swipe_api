from common.models import Subscription, Transaction
from config import SessionLocal


def test_legacy_init_is_gone_without_body_database_or_bank(client, monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("legacy endpoint attempted an external HTTP request")

    def fail_tbank_client(*args, **kwargs):
        raise AssertionError("legacy endpoint created the canonical T-Bank client")

    monkeypatch.setattr("requests.sessions.Session.request", fail_network)
    monkeypatch.setattr(
        "controllers.subscription_controller._tbank_client", fail_tbank_client
    )
    with SessionLocal() as session:
        before = session.query(Transaction).count()

    for body in (
        None,
        {},
        {
            "orderId": "attacker-order",
            "amount": 1,
            "price": 1,
            "currency": "USD",
            "duration": 9999,
            "customerKey": "other-user",
            "phone": "+70000000000",
            "subscriptionId": 1,
            "returnUrl": "https://attacker.example/return",
        },
    ):
        response = client.post("/subscriptions/init_payment", json=body)
        assert response.status_code == 410
        assert response.json() == {
            "detail": {
                "code": "LEGACY_PAYMENT_ENDPOINT_REMOVED",
                "message": "Use POST /subscriptions/checkout",
            }
        }

    with SessionLocal() as session:
        assert session.query(Transaction).count() == before


def test_openapi_marks_legacy_init_deprecated(client):
    operation = client.get("/openapi.json").json()["paths"][
        "/subscriptions/init_payment"
    ]["post"]
    assert operation["deprecated"] is True


def test_canonical_checkout_keeps_server_price(client):
    client.post("/auth/send_code", params={"phone_number": "70000000671"})
    registration = client.post(
        "/auth/register",
        json={
            "phone_number": "70000000671",
            "first_name": "Canonical",
            "last_name": "Checkout",
            "date_of_birth": "1995-01-01",
            "gender": "female",
            "city_name": "Демо-Сити (Демо-регион Север)",
        },
    )
    token = registration.json()["access_token"]
    headers = {"Authorization": token, "Idempotency-Key": "legacy-removal-key-01"}
    with SessionLocal() as session:
        plan = session.query(Subscription).filter(Subscription.price_minor > 0).first()
        plan_id, server_price = plan.id, plan.price_minor

    tampered = client.post(
        "/subscriptions/checkout",
        headers=headers,
        json={"subscription_id": plan_id, "amount": 1, "price": 1},
    )
    assert tampered.status_code == 422

    checkout = client.post(
        "/subscriptions/checkout",
        headers=headers,
        json={"subscription_id": plan_id},
    )
    assert checkout.status_code == 201, checkout.text
    assert checkout.json()["amount_minor"] == server_price

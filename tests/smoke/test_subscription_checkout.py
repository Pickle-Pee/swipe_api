from common.models import Subscription, Transaction
from config import SessionLocal


def _register(client, phone):
    sent = client.post("/auth/send_code", params={"phone_number": phone})
    assert sent.status_code == 200, sent.text
    response = client.post(
        "/auth/register",
        json={
            "phone_number": phone,
            "first_name": "Checkout",
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


def test_checkout_uses_database_price_is_idempotent_and_demo_has_no_network(
    client, monkeypatch
):
    headers = _register(client, "70000000881")
    plans = client.get("/subscriptions", headers=headers)
    assert plans.status_code == 200, plans.text
    plan = next(
        item for item in plans.json()["subscriptions"] if item["price_minor"] > 0
    )

    def fail_network(*args, **kwargs):
        raise AssertionError("demo checkout attempted external HTTP")

    monkeypatch.setattr("requests.sessions.Session.post", fail_network)
    checkout_headers = {**headers, "Idempotency-Key": "checkout-test-key-0001"}
    tampered = client.post(
        "/subscriptions/checkout",
        headers=checkout_headers,
        json={"subscription_id": plan["id"], "amount": 1, "currency": "USD"},
    )
    assert tampered.status_code == 422
    first = client.post(
        "/subscriptions/checkout",
        headers=checkout_headers,
        json={"subscription_id": plan["id"]},
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["amount_minor"] == plan["price_minor"]
    assert body["currency"] == "RUB"
    assert body["payment_url"].startswith("https://demo.swipe.local/")

    second = client.post(
        "/subscriptions/checkout",
        headers=checkout_headers,
        json={"subscription_id": plan["id"]},
    )
    assert second.status_code == 200
    assert second.json()["order_id"] == body["order_id"]
    with SessionLocal() as session:
        assert (
            session.query(Transaction).filter_by(order_id=body["order_id"]).count() == 1
        )
        transaction = (
            session.query(Transaction).filter_by(order_id=body["order_id"]).one()
        )
        assert transaction.amount_minor == plan["price_minor"]


def test_checkout_rejects_unknown_and_inactive_plans(client):
    headers = _register(client, "70000000882")
    common = {**headers, "Idempotency-Key": "checkout-test-key-0002"}
    assert (
        client.post(
            "/subscriptions/checkout", headers=common, json={"subscription_id": 999999}
        ).status_code
        == 404
    )
    with SessionLocal() as session:
        plan = session.query(Subscription).filter(Subscription.price_minor > 0).first()
        plan.is_active = False
        plan_id = plan.id
        session.commit()
    try:
        response = client.post(
            "/subscriptions/checkout",
            headers={**headers, "Idempotency-Key": "checkout-test-key-0003"},
            json={"subscription_id": plan_id},
        )
        assert response.status_code == 409
    finally:
        with SessionLocal() as session:
            session.query(Subscription).filter_by(id=plan_id).update(
                {"is_active": True}
            )
            session.commit()


def test_payment_status_is_owner_only_and_demo_can_change_result(client):
    owner = _register(client, "70000000883")
    other = _register(client, "70000000884")
    plan = next(
        item
        for item in client.get("/subscriptions", headers=owner).json()["subscriptions"]
        if item["price_minor"] > 0
    )
    created = client.post(
        "/subscriptions/checkout",
        headers={**owner, "Idempotency-Key": "checkout-test-key-0004"},
        json={"subscription_id": plan["id"]},
    ).json()
    order_id = created["order_id"]
    assert (
        client.get(f"/subscriptions/payments/{order_id}", headers=other).status_code
        == 404
    )
    changed = client.post(
        f"/subscriptions/demo/payments/{order_id}/success", headers=owner
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "succeeded"
    assert changed.json()["subscription_activated"] is False


def test_checkout_requires_idempotency_key(client):
    headers = _register(client, "70000000885")
    plan = next(
        item
        for item in client.get("/subscriptions", headers=headers).json()[
            "subscriptions"
        ]
        if item["price_minor"] > 0
    )
    assert (
        client.post(
            "/subscriptions/checkout",
            headers=headers,
            json={"subscription_id": plan["id"]},
        ).status_code
        == 422
    )


def test_demo_result_endpoint_is_hidden_outside_demo(client, monkeypatch):
    headers = _register(client, "70000000886")
    monkeypatch.setattr("controllers.subscription_controller.IS_DEMO", False)
    monkeypatch.setattr("controllers.subscription_controller.IS_PRODUCTION", True)
    response = client.post(
        "/subscriptions/demo/payments/does-not-matter/success",
        headers=headers,
    )
    assert response.status_code == 404

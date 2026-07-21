import logging

from common.services import generate_tbank_token


TERMINAL = "secure-log-terminal"
PASSWORD = "secure-log-password"


def _register(client, phone):
    client.post("/auth/send_code", params={"phone_number": phone})
    response = client.post(
        "/auth/register",
        json={
            "phone_number": phone,
            "first_name": "Secure",
            "last_name": "Logging",
            "date_of_birth": "1995-01-01",
            "gender": "female",
            "city_name": "Демо-Сити (Демо-регион Север)",
        },
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _assert_absent(logs, *secrets):
    for secret in secrets:
        assert secret not in logs


def test_auth_refresh_does_not_log_tokens(client, caplog, capsys):
    tokens = _register(client, "70000000661")
    caplog.clear()
    capsys.readouterr()
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/auth/refresh_token",
            params={"refresh_token": tokens["refresh_token"]},
        )
    assert response.status_code == 200, response.text
    refreshed = response.json()
    captured = capsys.readouterr()
    output = caplog.text + captured.out + captured.err
    _assert_absent(
        output,
        tokens["access_token"],
        tokens["refresh_token"],
        refreshed["access_token"],
        refreshed["refresh_token"],
    )


def test_checkout_and_webhooks_never_log_payment_secrets(client, monkeypatch, caplog):
    tokens = _register(client, "70000000662")
    headers = {"Authorization": tokens["access_token"]}
    plan = next(
        item
        for item in client.get("/subscriptions", headers=headers).json()[
            "subscriptions"
        ]
        if item["price_minor"] > 0
    )
    caplog.clear()
    with caplog.at_level(logging.INFO):
        checkout = client.post(
            "/subscriptions/checkout",
            headers={**headers, "Idempotency-Key": "secure-log-checkout-01"},
            json={"subscription_id": plan["id"]},
        )
    assert checkout.status_code == 201, checkout.text
    checkout_body = checkout.json()
    _assert_absent(caplog.text, checkout_body["payment_url"])

    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_KEY", TERMINAL
    )
    monkeypatch.setattr(
        "controllers.subscription_controller.TBANK_TERMINAL_PASSWORD", PASSWORD
    )
    rebill_id = "rebill-value-that-must-not-appear"
    card_id = "card-value-that-must-not-appear"
    payload = {
        "TerminalKey": TERMINAL,
        "OrderId": checkout_body["order_id"],
        "PaymentId": checkout_body["payment_id"],
        "Status": "CONFIRMED",
        "Amount": checkout_body["amount_minor"],
        "Success": True,
        "ErrorCode": "0",
        "RebillId": rebill_id,
        "CardId": card_id,
        "Pan": "4300000000000777",
        "DATA": {"Phone": "+70000000662"},
        "Receipt": {"Email": "buyer@example.com"},
    }
    payload["Token"] = generate_tbank_token(payload, PASSWORD)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = client.post("/subscriptions/webhooks/tbank", json=payload)
    assert response.status_code == 200 and response.text == "OK"
    _assert_absent(
        caplog.text,
        rebill_id,
        card_id,
        payload["Pan"],
        payload["Token"],
        PASSWORD,
        TERMINAL,
        "+70000000662",
        "buyer@example.com",
        checkout_body["payment_id"],
    )

    invalid_token = "invalid-bank-token-that-must-not-appear"
    payload["Token"] = invalid_token
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = client.post("/subscriptions/webhooks/tbank", json=payload)
    assert response.status_code == 403
    _assert_absent(caplog.text, invalid_token, rebill_id, card_id, TERMINAL)

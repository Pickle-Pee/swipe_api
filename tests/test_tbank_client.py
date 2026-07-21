import hashlib

import pytest
import requests

from common.services.tbank_client import (
    TBankClient,
    TBankClientError,
    TBankInitRequest,
    generate_tbank_token,
)


def test_token_uses_sorted_root_scalars_and_excludes_nested_fields():
    params = {
        "TerminalKey": "TinkoffBankTest",
        "Amount": 19200,
        "OrderId": "21090",
        "Description": "Подарочная карта на 1000 рублей",
        "DATA": {"Email": "customer@example.com"},
        "Receipt": {"Items": []},
    }
    source = "19200Подарочная карта на 1000 рублей21090passwordTinkoffBankTest"
    assert (
        generate_tbank_token(params, "password")
        == hashlib.sha256(source.encode("utf-8")).hexdigest()
    )


def test_token_is_independent_of_input_order_and_ignores_existing_token():
    first = {"PaymentId": "1", "TerminalKey": "T", "Token": "old"}
    second = {"TerminalKey": "T", "PaymentId": "1"}
    assert generate_tbank_token(first, "secret") == generate_tbank_token(
        second, "secret"
    )


class FakeResponse:
    def __init__(self, data, status_error=None):
        self.data = data
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def client(session):
    return TBankClient(
        base_url="https://securepay.tinkoff.ru/v2",
        terminal_key="terminal",
        password="password",
        timeout_seconds=3,
        session=session,
    )


def test_init_success_is_typed_and_does_not_return_secret():
    session = FakeSession(
        FakeResponse(
            {
                "Success": True,
                "PaymentId": "123",
                "PaymentURL": "https://pay.example/123",
                "Status": "NEW",
            }
        )
    )
    result = client(session).init_payment(
        TBankInitRequest(49900, "order", "Plan", "42")
    )
    assert result.payment_id == "123"
    assert result.payment_url == "https://pay.example/123"
    payload = session.calls[0][1]["json"]
    assert payload["Amount"] == 49900
    assert payload["Token"]
    assert "Password" not in payload
    assert session.calls[0][1]["timeout"] == 3


def test_init_failure_is_sanitized():
    session = FakeSession(
        FakeResponse({"Success": False, "ErrorCode": "7", "Message": "provider detail"})
    )
    with pytest.raises(TBankClientError, match="rejected") as error:
        client(session).init_payment(TBankInitRequest(49900, "order", "Plan", "42"))
    assert error.value.code == "7"
    assert "provider detail" not in str(error.value)


def test_init_timeout_is_retryable():
    with pytest.raises(TBankClientError) as error:
        client(FakeSession(error=requests.Timeout())).init_payment(
            TBankInitRequest(49900, "order", "Plan", "42")
        )
    assert error.value.retryable is True
    assert error.value.code == "provider_timeout"

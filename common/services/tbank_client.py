from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import requests


class TBankClientError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def generate_tbank_token(params: dict[str, Any], password: str) -> str:
    """Sign root scalar fields; nested DATA/Receipt values are excluded."""
    if not password:
        raise ValueError("T-Bank terminal password is not configured")
    values = {
        key: value
        for key, value in params.items()
        if key != "Token"
        and value is not None
        and not isinstance(value, (dict, list, tuple, set))
    }
    values["Password"] = password

    def stringify(value: Any) -> str:
        return str(value).lower() if isinstance(value, bool) else str(value)

    source = "".join(stringify(values[key]) for key in sorted(values))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TBankInitRequest:
    amount_minor: int
    order_id: str
    description: str
    customer_key: str


@dataclass(frozen=True)
class TBankInitResult:
    payment_id: str
    payment_url: str
    status: str


class TBankClient:
    def __init__(
        self,
        *,
        base_url: str,
        terminal_key: str | None,
        password: str | None,
        notification_url: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
        recurrent_enabled: bool = False,
        timeout_seconds: float = 10,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.terminal_key = terminal_key
        self.password = password
        self.notification_url = notification_url
        self.success_url = success_url
        self.fail_url = fail_url
        self.recurrent_enabled = recurrent_enabled
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def init_payment(self, request: TBankInitRequest) -> TBankInitResult:
        if not self.terminal_key or not self.password:
            raise TBankClientError(
                "provider_not_configured", "Payment provider is not configured"
            )
        payload: dict[str, Any] = {
            "TerminalKey": self.terminal_key,
            "Amount": request.amount_minor,
            "OrderId": request.order_id,
            "Description": request.description[:140],
            "CustomerKey": request.customer_key,
            "PayType": "O",
        }
        for key, value in (
            ("NotificationURL", self.notification_url),
            ("SuccessURL", self.success_url),
            ("FailURL", self.fail_url),
        ):
            if value:
                payload[key] = value
        if self.recurrent_enabled:
            payload["Recurrent"] = "Y"
            payload["DATA"] = {"OperationInitiatorType": "1"}
        payload["Token"] = generate_tbank_token(payload, self.password)
        try:
            response = self.session.post(
                f"{self.base_url}/Init", json=payload, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise TBankClientError(
                "provider_timeout", "Payment provider timed out", retryable=True
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            raise TBankClientError(
                "provider_unavailable",
                "Payment provider is unavailable",
                retryable=True,
            ) from exc
        if not data.get("Success"):
            raise TBankClientError(
                str(data.get("ErrorCode") or "init_failed"),
                "Payment initialization was rejected",
            )
        payment_id, payment_url = data.get("PaymentId"), data.get("PaymentURL")
        if payment_id is None or not isinstance(payment_url, str) or not payment_url:
            raise TBankClientError(
                "invalid_provider_response",
                "Payment provider returned an invalid response",
            )
        return TBankInitResult(
            str(payment_id), payment_url, str(data.get("Status") or "NEW")
        )

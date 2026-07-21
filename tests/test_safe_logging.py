import io
import logging

from safe_logging import (
    REDACTED,
    RedactingFilter,
    RedactingFormatter,
    mask_identifier,
    redact,
    redact_text,
)


SECRETS = {
    "access_token": "access-secret-value",
    "refresh_token": "refresh-secret-value",
    "Token": "bank-token-value",
    "Password": "terminal-password-value",
    "TerminalKey": "terminal-key-value",
    "RebillId": "rebill-secret-value",
    "PaymentURL": "https://pay.example/form?secret=value",
    "CardId": "card-secret-value",
    "Pan": "4300000000000777",
    "DATA": {"Phone": "+70000000000"},
    "Receipt": {"Email": "buyer@example.com"},
}


def test_redact_recursively_removes_sensitive_values():
    result = redact({"safe": "visible", "nested": SECRETS})
    assert result["safe"] == "visible"
    assert all(value == REDACTED for value in result["nested"].values())


def test_redact_text_handles_labels_assignments_bearer_and_jwt():
    message = (
        'Token="bank-token-value" RebillId rebill-secret-value '
        "refresh_token=refresh-secret-value Bearer access-secret-value "
        "eyJheader.payload.signature"
    )
    redacted = redact_text(message)
    for secret in (
        "bank-token-value",
        "rebill-secret-value",
        "refresh-secret-value",
        "access-secret-value",
        "eyJheader.payload.signature",
    ):
        assert secret not in redacted


def test_logging_filter_and_formatter_redact_message_args_and_exception():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("safe-logging-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        raise RuntimeError("PaymentURL=https://pay.example/private?token=secret")
    except RuntimeError:
        logger.exception("payload=%s", SECRETS)
        logger.info("Token=%s", "positional-bank-token")

    output = stream.getvalue()
    for secret in SECRETS.values():
        if isinstance(secret, str):
            assert secret not in output
    assert "https://pay.example/private" not in output
    assert "positional-bank-token" not in output
    assert REDACTED in output


def test_payment_identifier_is_masked():
    assert mask_identifier("123456789012") == "1234...9012"
    assert mask_identifier("123") == REDACTED

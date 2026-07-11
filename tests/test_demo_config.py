import importlib
import io
import sys

import pytest


def load_config(monkeypatch, **values):
    monkeypatch.setenv("APP_ENV", values.pop("APP_ENV", "demo"))
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("config", None)
    return importlib.import_module("config")


def test_demo_uses_safe_defaults_and_local_storage(monkeypatch, tmp_path):
    config = load_config(
        monkeypatch,
        DEMO_STORAGE_DIR=str(tmp_path),
        DATABASE_URL="",
        ASYNC_DATABASE_URL="",
        SECRET_KEY="",
    )

    assert config.IS_DEMO is True
    assert config.SECRET_KEY == "demo-secret-key-not-for-production"

    config.s3_client.upload_fileobj(io.BytesIO(b"demo"), "photos", "avatar.jpg")
    stored = config.s3_client.get_object(Bucket="photos", Key="avatar.jpg")
    try:
        assert stored["Body"].read() == b"demo"
    finally:
        stored["Body"].close()


def test_production_lists_missing_secrets(monkeypatch):
    required = [
        "DATABASE_URL", "ASYNC_DATABASE_URL", "SECRET_KEY",
        "DADATA_API_TOKEN", "DADATA_API_SECRET", "DADATA_API_URL",
        "YANDEX_KEY_ID", "YANDEX_KEY", "BUCKET_MESSAGE_IMAGES",
        "BUCKET_MESSAGE_VOICES", "BUCKET_PROFILE_IMAGES", "BUCKET_VERIFY_IMAGES",
        "SMS_CENTER_LOGIN", "SMS_CENTER_PASSWORD", "SMS_SENDER",
        "FIREBASE_CREDENTIALS_PATH", "TBANK_KASSA_PASSWORD", "TBANK_KASSA_TERMINAL",
    ]
    values = {name: "" for name in required}

    with pytest.raises(RuntimeError, match="DATABASE_URL.*FIREBASE_CREDENTIALS_PATH"):
        load_config(monkeypatch, APP_ENV="production", **values)


@pytest.mark.asyncio
async def test_demo_push_does_not_call_external_service(monkeypatch, tmp_path):
    load_config(monkeypatch, DEMO_STORAGE_DIR=str(tmp_path), PUSH_URL="http://invalid")
    for name in list(sys.modules):
        if name == "common.utils" or name.startswith("common.utils."):
            sys.modules.pop(name, None)

    service_utils = importlib.import_module("common.utils.service_utils")

    def fail_request(*_args, **_kwargs):
        raise AssertionError("external push request attempted in demo mode")

    monkeypatch.setattr(service_utils.requests, "post", fail_request)
    result = await service_utils.send_push_notification("token", "title", "body", {})

    assert result is None


def test_demo_payment_state_does_not_call_provider(monkeypatch, tmp_path):
    load_config(monkeypatch, DEMO_STORAGE_DIR=str(tmp_path))
    for name in list(sys.modules):
        if name == "common.utils" or name.startswith("common.utils."):
            sys.modules.pop(name, None)

    subscription_utils = importlib.import_module("common.utils.subscription_utils")

    def fail_request(*_args, **_kwargs):
        raise AssertionError("external payment request attempted in demo mode")

    monkeypatch.setattr(subscription_utils.requests, "post", fail_request)
    result = subscription_utils.get_payment_info_from_tinkoff("demo-payment")

    assert result["Demo"] is True
    assert result["Status"] == "CONFIRMED"

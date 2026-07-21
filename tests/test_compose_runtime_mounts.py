import re
from pathlib import Path


COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
RUNTIME_SERVICES = ("main_app", "socket_app", "push_app", "admin_app")


def _service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        compose,
    )
    assert match is not None, f"service {service} is missing from Compose"
    return match.group(1)


def test_runtime_services_mount_shared_config_outside_app_source() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "./config.py:/app/config.py" not in compose
    assert "./safe_logging.py:/app/safe_logging.py" not in compose

    for service in RUNTIME_SERVICES:
        block = _service_block(compose, service)
        assert "PYTHONPATH: /opt/swipe:/app" in block
        assert "./config.py:/opt/swipe/config.py:ro" in block
        assert "./safe_logging.py:/opt/swipe/safe_logging.py:ro" in block

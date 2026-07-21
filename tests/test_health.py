import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("service_dir", "module_name", "application_name", "service_name"),
    [
        ("main_app", "app", "app", "main_app"),
        ("socket_app", "app", "fastapi_app", "socket_app"),
        ("push_app", "app", "app", "push_app"),
        ("admin_app", "app.main", "app", "admin_app"),
    ],
)
def test_health_endpoint(service_dir, module_name, application_name, service_name):
    code = (
        "from fastapi.testclient import TestClient; "
        f"from {module_name} import {application_name}; "
        f"response = TestClient({application_name}).get('/health'); "
        "assert response.status_code == 200; "
        f"assert response.json() == {{'status': 'ok', 'service': '{service_name}'}}"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "demo",
            "DATABASE_URL": "",
            "ASYNC_DATABASE_URL": "",
            "SECRET_KEY": "",
            "FIREBASE_CREDENTIALS_PATH": "",
            "DEMO_STORAGE_DIR": str(ROOT / ".demo_storage_test"),
            "PYTHONPATH": str(ROOT),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT / service_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr

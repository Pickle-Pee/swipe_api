from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[2]
MAIN_APP = ROOT / "main_app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(MAIN_APP) not in sys.path:
    sys.path.insert(0, str(MAIN_APP))

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://swipe:swipe@localhost:5432/swipe_smoke_test",
)
test_url = make_url(TEST_DATABASE_URL)
if (
    not test_url.database
    or not test_url.database.endswith("_test")
    or not re.fullmatch(r"[A-Za-z0-9_]+", test_url.database)
):
    raise RuntimeError("TEST_DATABASE_URL database name must end with '_test'")

os.environ.update(
    {
        "APP_ENV": "demo",
        "DATABASE_URL": TEST_DATABASE_URL,
        "ASYNC_DATABASE_URL": TEST_DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        ),
        "ALEMBIC_DEV_URL": TEST_DATABASE_URL,
        "ENVIRONMENT": "dev",
        "DEMO_STORAGE_DIR": str(
            Path(tempfile.gettempdir()) / "swipe_api_demo_storage_test"
        ),
        "BUCKET_PROFILE_IMAGES": "profile-images",
        "SECRET_KEY": "smoke-test-secret-key-with-32-bytes-minimum",
    }
)


@pytest.fixture(scope="session", autouse=True)
def isolated_database():
    admin_url = test_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    database_name = test_url.database
    with admin_engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    alembic_config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")

    from scripts.seed_demo import seed_demo

    seed_demo()
    yield

    from config import asyncEngine, engine

    engine.dispose()
    try:
        import asyncio

        asyncio.run(asyncEngine.dispose())
    except RuntimeError:
        pass
    with admin_engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def client(isolated_database):
    from app import app

    with TestClient(app) as test_client:
        yield test_client

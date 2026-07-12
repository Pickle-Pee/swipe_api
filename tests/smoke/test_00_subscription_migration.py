from pathlib import Path

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[2]


def test_subscription_migration_downgrade_and_upgrade(isolated_database):
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "-1")
    command.upgrade(config, "head")

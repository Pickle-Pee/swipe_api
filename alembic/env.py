import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Добавление корневой директории проекта в sys.path для корректного импорта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Загрузка переменных окружения из .env файла
env_file = os.getenv('ENV_FILE', '.env')
load_dotenv(env_file)

# Импорт Base и моделей
from config import Base

from common.models import (
    admin_models,
    auth_models,
    cities_models,
    communication_models,
    error_models,
    interests_models,
    likes_models,
    subscriptions_models,
    user_models
)

# Функция для получения URL базы данных на основе переменной окружения
def get_url():
    env = os.getenv('ENVIRONMENT', 'dev')  # По умолчанию 'dev'
    variable_name = 'ALEMBIC_PROD_URL' if env == 'prod' else 'ALEMBIC_DEV_URL'
    url = os.getenv(variable_name)
    if not url:
        raise RuntimeError(f'{variable_name} must be set before running Alembic')
    return url

# Получение конфигурации Alembic
config = context.config

# Установка динамического URL для SQLAlchemy
config.set_main_option('sqlalchemy.url', get_url())

# Настройка логирования из конфигурационного файла Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Указание метаданных модели для автогенерации миграций
target_metadata = Base.metadata

# Функция для исключения определённых объектов из миграций
def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name == "spatial_ref_sys":
        return False
    return True

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

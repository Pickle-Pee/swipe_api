# Swipe API

Backend MVP приложения знакомств. Репозиторий содержит основной FastAPI API, Socket.IO сервис, Firebase push-сервис и административный API с общей PostgreSQL-моделью.

Текущее техническое состояние и известные блокеры описаны в `docs/BASELINE.md`, продуктовый объём — в `docs/PROJECT_CONTEXT.md`.

## Требования

- Python 3.11;
- PostgreSQL;
- Redis;
- системные build tools для `dlib`/`face-recognition`;
- `libmagic` на Linux; на Windows устанавливается `python-magic-bin`;
- Docker Desktop — опционально, Docker-сценарий будет завершён отдельной задачей.

На Windows для сборки некоторых пакетов нужны Microsoft C++ Build Tools. Все Docker images используют Python 3.11.

## Установка

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Для разработки:

```powershell
python -m pip install -r requirements-dev.txt
```

Не коммитьте `.env`, Firebase service-account JSON, ключи и signing-файлы. Для локального demo скопируйте безопасный шаблон:

```powershell
Copy-Item .env.example .env
```

При `APP_ENV=demo` SMS и push не отправляются, платёжный провайдер и scheduler автоплатежей не вызываются, а S3 заменяется каталогом `.demo_storage`. Demo verification code задаётся через `DEMO_VERIFICATION_CODE` и возвращается только в demo. Значения demo по умолчанию запрещено использовать в production.

`APP_ENV=production` выполняет fail-fast проверку обязательных DB, SMS, Firebase, S3, DaData и Т-Банк параметров и перечисляет отсутствующие имена без вывода значений.

## Проверки

```powershell
python -m pip check
python -m compileall -q admin_app common main_app push_app socket_app
ruff check admin_app common main_app push_app socket_app config.py
ruff format --check admin_app common main_app push_app socket_app config.py
pytest
```

Автоматических тестов в исходном baseline нет, поэтому `pytest` пока сообщает, что тесты не найдены. Это известное ограничение, а не причина отключать команду в CI.

Ruff подключён как диагностический инструмент. Исходный legacy-код пока не проходит его полностью: baseline содержит 170 lint-нарушений и 46 файлов, требующих форматирования. Их массовое исправление вынесено из задачи нормализации зависимостей, чтобы не смешивать механический рефакторинг с runtime-изменениями.

## Запуск без Docker

Корень репозитория должен присутствовать в `PYTHONPATH`. Также нужны безопасно настроенные PostgreSQL, Redis и переменные окружения.

```powershell
$env:PYTHONPATH = (Get-Location).Path

Push-Location main_app
python app.py
Pop-Location

Push-Location socket_app
python app.py
Pop-Location

Push-Location push_app
python app.py
Pop-Location

Push-Location admin_app
uvicorn app.main:app --host 0.0.0.0 --port 1027
Pop-Location
```

Порты:

- main API: `1024`;
- Socket.IO: `1025`;
- push API: `1026`;
- admin API: `1027`;
- Redis: `6379`.

## База данных

Приложения не вызывают `Base.metadata.create_all()`. Схема должна применяться Alembic:

```powershell
alembic upgrade head
alembic current
alembic check
```

Для создания следующей миграции и отката одного шага:

```powershell
alembic revision --autogenerate -m "описание изменения"
alembic downgrade -1
```

Alembic требует `ENVIRONMENT=dev` и `ALEMBIC_DEV_URL` (либо
`ENVIRONMENT=prod` и `ALEMBIC_PROD_URL`). Не запускайте миграции на URL из
неизвестного `.env`. Активная baseline-миграция находится в
`alembic/current_versions`; прежняя неполная история сохранена в
`alembic/versions` только для аудита и не выполняется.

## Docker Compose

Статическая проверка без печати развёрнутых секретов:

```powershell
docker compose config --quiet
```

После включения виртуализации и запуска Docker Desktop весь demo-backend запускается одной командой:

```powershell
docker compose up --build
```

Compose поднимает PostgreSQL 16, Redis 7, одноразовый сервис `migrate`, main,
socket, push и admin API. `migrate` выполняет `alembic upgrade head` после
готовности PostgreSQL; приложения запускаются только после успешной миграции.
PostgreSQL, Redis и все приложения имеют healthchecks. Данные PostgreSQL,
Redis и локальные demo-файлы хранятся в named volumes.

Проверка состояния и логов:

```powershell
docker compose ps
docker compose logs --no-color
```

Остановка с сохранением данных:

```powershell
docker compose down
```

Полная очистка demo-данных выполняется только явно:

```powershell
docker compose down --volumes --remove-orphans
```

Автоматическое создание таблиц через SQLAlchemy намеренно отсутствует. Схемой
управляет только Alembic через сервис `migrate`.

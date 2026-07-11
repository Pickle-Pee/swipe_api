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

Не коммитьте `.env`, Firebase service-account JSON, ключи и signing-файлы. Полный безопасный `.env.example` и demo-конфигурация появятся в следующей задаче. До этого не используйте production/dev credentials для smoke-тестов.

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
```

Не запускайте миграции на URL из неизвестного `.env`. Проверка существующей цепочки миграций на новой локальной PostgreSQL будет выполнена отдельной задачей.

## Docker Compose

Статическая проверка без печати развёрнутых секретов:

```powershell
docker compose config --quiet
```

Полная сборка отложена до включения виртуализации и запуска Docker Desktop:

```powershell
docker compose build
docker compose up
```

Текущий Compose ещё не содержит локальный PostgreSQL и healthchecks; это объём следующей Docker-задачи.

# Baseline текущего состояния

Дата аудита: 12 июля 2026. Ревизия: `247d3c9` (`first commit`). Ветка аудита: `codex/backend-baseline`. В рамках аудита код приложения не исправлялся.

## Структура и точки запуска

| Компонент | Точка входа | Команда из образа | Порт |
|---|---|---|---:|
| Main API | `main_app/app.py`, объект `app` | `python app.py` | 1024 |
| Socket.IO | `socket_app/app.py`, объект `socket_app` | `python app.py` | 1025 |
| Push API | `push_app/app.py`, объект `app` | `python app.py` | 1026 |
| Admin API | `admin_app/app/main.py`, объект `app` | `uvicorn app.main:app --host 0.0.0.0 --port 1027` | 1027 |

Локальные эквиваленты запуска из корня требуют корректного `PYTHONPATH`, заполненного `.env`, доступных PostgreSQL/Redis и credentials интеграций. Main и socket запускаются как скрипты из соответствующих каталогов; admin — из `admin_app`. Формально возможные команды:

```text
cd main_app; python app.py
cd socket_app; python app.py
cd push_app; python app.py
cd admin_app; uvicorn app.main:app --host 0.0.0.0 --port 1027
```

Они не являются полностью воспроизводимым локальным сценарием: см. оставшиеся блокеры ниже. Socket содержит незарегистрированную функцию `startup_event()` для Redis listener. Scheduler стартует только в ветке `__main__` main-сервиса. Runtime-вызовы `Base.metadata.create_all()` удалены; схема должна применяться Alembic.

## Модель и миграции БД

SQLAlchemy описывает пользователей, атрибуты, фотографии, геолокацию, push-токены, очередь верификации, интересы, likes/dislikes/favorites, чаты, сообщения/медиа/голосовые сообщения, приглашения, подписки, транзакции, города/регионы и admin users.

В репозитории семь исходных миграций, образующих одну линейную цепочку:

```text
3ece68983ddb -> 3ef1b88ab814 -> b72e72841a97 -> 731ee7749873
-> d14a0f02ae61 -> 081a1f71838f -> 5c0b937bc038
```

`alembic/env.py` выбирает `ALEMBIC_DEV_URL` или `ALEMBIC_PROD_URL` по `ENVIRONMENT`. `alembic.ini` не содержит URL. В дереве присутствуют `.pyc` ранее существовавших, но отсутствующих исходных миграций — это признак утраченной/переписанной истории и риск для уже развёрнутых БД. Проверка upgrade на чистой БД не выполнена: Compose не предоставляет PostgreSQL, а подключаться к URL из локального `.env` небезопасно.

Runtime-вызовы `create_all` удалены из main/socket/admin. Управление схемой оставлено Alembic; перед запуском на чистой БД требуется документированный `alembic upgrade head`.

## Версии инструментов и зависимостей

- Среда аудита: Windows, Python 3.12.13, pip 26.0.1.
- Dockerfile main/socket: `python:3.9-slim`.
- Dockerfile push/admin: `python:3.11`.
- Docker Desktop найден по абсолютному пути после установки пользователем: Docker 29.6.1, Docker Compose 5.2.0. Текущий процесс Codex ещё не видит команду через `PATH`.
- `requirements.txt`: 58 строк, преимущественно без версий; явно закреплены только `python-telegram-bot==13.9`, `python-dotenv==1.0.0`, `openai==1.37.0`.
- Повторяются `python-dotenv`, `python-multipart`, `passlib`; одновременно указаны `psycopg2` и `psycopg2-binary`, `python-jose` и устаревший отдельный пакет `jose`.
- `face-recognition` добавлен в `requirements.txt`; для совместимости его models с `pkg_resources` добавлен `setuptools<81`.
- Lock-файл отсутствует, поэтому получаемый набор меняется со временем и между Python 3.9/3.11.

Поддерживаемый runtime зафиксирован как Python 3.11; все четыре Dockerfile используют `python:3.11`/`python:3.11-slim`. Чистая локальная приёмка дополнительно выполнена на доступном Python 3.12.13.

`requirements.txt` очищен от дублей и конфликтующих реализаций (`jose`, исходный `psycopg2`, повторные `python-dotenv`, `python-multipart`, `passlib`) и закреплён по версиям. Добавлены фактически необходимые `alembic`, `httpx`, `face-recognition`, compatibility pin `setuptools` и платформенный выбор `python-magic`. `requirements-dev.txt` содержит pytest, pytest-asyncio и Ruff.

Команда `python -m pip install --dry-run --ignore-installed -r requirements.txt` после разрешения сетевого доступа завершилась с кодом 0 на Python 3.12. Первая реальная установка в новом игнорируемом `.venv` завершилась с кодом 1: сборка wheel `pywatchman==4.0.0` требовала Microsoft Visual C++ 14.0+. После установки пользователем системных build-зависимостей повторная команда `python -m pip install -r requirements.txt` завершилась успешно (код 0); `pip check` также завершился успешно. Значит, requirements устанавливается на проверенной Windows/Python 3.12 машине при наличии C++ toolchain, но эта системная предпосылка не документирована проектом.

Для Windows `python-magic-bin` и для Linux `python-magic` выбираются environment markers. Это устраняет локальное отсутствие `libmagic` DLL без изменения Linux/Docker runtime. Установка обоих requirements-файлов с нуля в `.venv-deps-check` завершилась успешно.

## Переменные окружения

Код или миграции читают следующие переменные:

```text
DATABASE_URL, ASYNC_DATABASE_URL, SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_HOURS, MAX_DISTANCE
REDIS_HOST, REDIS_PORT
MAIN_APP_HOST
DADATA_API_TOKEN, DADATA_API_SECRET, DADATA_API_URL
YANDEX_KEY_ID, YANDEX_KEY
BUCKET_MESSAGE_IMAGES, BUCKET_MESSAGE_VOICES, BUCKET_PROFILE_IMAGES, BUCKET_VERIFY_IMAGES
SMS_API_KEY, SMS_CENTER_LOGIN, SMS_CENTER_PASSWORD, SMS_SENDER
FIREBASE_CREDENTIALS_PATH
VERIFY_CHAT_LINK, VERIFY_CHAT_ID, VERIFY_SEND_TEXT
OPEN_API_KEY
TBANK_KASSA_PASSWORD, TBANK_KASSA_TERMINAL
ENV_FILE, ENVIRONMENT, ALEMBIC_DEV_URL, ALEMBIC_PROD_URL
```

Локальный игнорируемый `.env` также объявляет `MAIN_APP_PORT`, `MATCHES_APP_HOST`, `MATCHES_APP_PORT`, `BOT_SECRET_TOKEN`, `APP_ENV`, `API_URL`, `SOCKET_URL`, `PUSH_URL`; прямое использование всех этих имён кодом не подтверждено. Значения и наличие секретов намеренно не документируются. В локальном `.env` отсутствуют три `DADATA_*`, которые читает `config.py`. Обязательные числовые значения преобразуются при импорте без проверки и понятной диагностики.

`.env` корректно исключён `.gitignore` и не отслеживается Git. Шаблона `.env.example` нет. Firebase Admin service-account файлы исключены шаблоном `*-firebase-adminsdk-*.json`; Android `google-services.json` не подходит для Admin SDK. `tkassa_public.pem` в репозитории отсутствует. Каталог `wheels/` больше не требуется Dockerfile.

## Docker Compose

Compose описывает `redis`, `main_app`, `socket_app`, `push_app`, `admin_app`, общую bridge-сеть и порты 6379/1024–1027. Все приложения получают `.env`, `REDIS_HOST=redis`, `REDIS_PORT=6379`; исходники и `config.py` монтируются volumes.

Проверка `docker compose config` через абсолютный путь Docker CLI выполнена успешно (код 0). Compose 5.2.0 сообщил, что поле `version` устарело и игнорируется. Команда также развернула реальные значения из `.env` в вывод, поэтому все присутствовавшие там credentials следует считать раскрытыми и ротировать; значения в документацию не перенесены. Сборка и запуск намеренно не выполнялись, поскольку конфигурация указывает на внешние БД/сервисы и содержит реальные production/dev credentials. Статический аудит выявил блокеры:

- PostgreSQL-сервис и volume отсутствуют; `DATABASE_URL` должен указывать на внешнюю БД.
- Main/socket Dockerfile устанавливают зависимости напрямую из `requirements.txt`; зависимость от отсутствующего `wheels/` удалена.
- Main Dockerfile содержит подозрительный пробел после continuation `libmagic1 \\  `, способный нарушить инструкцию `RUN`.
- Push/Admin копируют весь репозиторий, но Compose затем монтирует только каталог конкретного сервиса в `/app` плюс `common` и `config.py`.
- Push и socket helpers используют адрес `localhost:1026`; внутри отдельного контейнера это не имя push-сервиса.
- Нет healthchecks, `depends_on`, restart policy и проверки готовности Redis/БД.
- Устаревшее поле Compose `version` удалено; `redis:latest` остаётся floating image.
- CI ссылается на отсутствующие `docker-compose.dev.yml` и `docker-compose.prod.yml` и запускает отсутствующий `pytest`-набор.

## Существующие тесты и проверки

Тестовых файлов, `pytest.ini`, `pyproject.toml`, `tox.ini` или test fixtures не найдено. Pytest и pytest-asyncio добавлены в `requirements-dev.txt`; запуск завершается без найденных тестов. CI-команда `docker-compose run --rm main_app pytest` пока не проверяет поведение приложения.

Выполнено:

```text
python -m compileall -q admin_app common main_app push_app socket_app
```

Результат: код 0, синтаксическая компиляция всех `.py` успешна. Это не импортирует модули и не проверяет endpoints.

Обязательные импорты повторно запущены после успешной установки, с безопасно переопределёнными локальными URL и фиктивными credentials, чтобы исключить обращения к реальным сервисам:

```text
python -c "import config"          -> успешно
main_app: python -c "import app"   -> успешно
socket_app: python -c "import app" -> успешно
push_app: python -c "import app"   -> успешно с локальным игнорируемым Firebase credential
admin_app: python -c "import app.main" -> успешно без подключения к PostgreSQL
```

Для импортов `PYTHONPATH` содержал корень репозитория, как это предполагает Compose. Все четыре приложения импортируются с безопасными локальными DB/S3-значениями и локальным игнорируемым Firebase credential. `orm_mode` заменён на `from_attributes`, предупреждение Pydantic 2 устранено. Сторонний `face_recognition_models 0.3.0` всё ещё предупреждает о deprecated `pkg_resources`; `setuptools<81` сохраняет работоспособность до обновления upstream.

Ruff добавлен как dev-линтер/форматтер. Диагностический baseline: `ruff check` находит 170 существующих нарушений, `ruff format --check` — 46 требующих форматирования файлов. Массовое исправление не выполнялось в задаче зависимостей.

Обязательный `docker compose config --quiet` успешно выполнен абсолютной командой Docker. После удаления поля `version` предупреждений нет. Полный вывод небезопасно раскрывает значения `.env`; повторять его в логах нельзя.

### Команды воспроизведения baseline

```text
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import config"

cd main_app; ..\.venv\Scripts\python.exe -c "import app"
cd socket_app; ..\.venv\Scripts\python.exe -c "import app"
cd push_app; ..\.venv\Scripts\python.exe -c "import app"
cd admin_app; ..\.venv\Scripts\python.exe -c "import app.main"

docker compose config
```

## Найденные ошибки и блокеры

Критические для локального demo:

1. Нет локального PostgreSQL и безопасной demo/test конфигурации.
2. `docker compose build main_app socket_app` не дошёл до чтения Dockerfile: Docker Desktop daemon не запущен (`docker_engine` named pipe отсутствует). Проверку сборки без `wheels/` нужно повторить после запуска Docker Desktop.
3. Push не стартует без корректного Firebase Admin service-account credential; SMS, S3 и платежи также не имеют demo-адаптеров/общего demo-флага.
4. Нет seed-данных и сценария подготовки городов, интересов, анкет и подписок.
5. Нет автоматических тестов целевого пути.
6. Не закреплены версии большинства зависимостей; для `face-recognition` добавлен только необходимый compatibility pin `setuptools<81`.

Значимые риски:

- Специальный номер `79000000000` и статический код `834721` всегда активны, не защищены environment-флагом и код возвращается клиенту; это production-риск.
- CORS допускает `*` вместе с credentials.
- Socket объявляет, но не регистрирует startup handler для Redis listener; runtime `create_all` удалён.
- Push service синхронно вызывает Firebase внутри async endpoint; helper main/socket обращается к `localhost`, что неверно для Compose.
- Socket.IO хранит подключения в process memory, допускает `no-auth` по query/header-маркеру и содержит широкие exception handlers; масштабирование и границы доверия не определены.
- Matching содержит захардкоженные исключаемые телефонные номера, возвращает `match_percentage=0` и пустые интересы.
- В source/README видны устаревшие production IP/домены и GitLab boilerplate; пользовательской документации запуска нет.
- Scheduler реальных рекуррентных платежей запускается вместе с main при script-start и не изолирован demo-конфигурацией.
- `README.md` — стандартный GitLab шаблон, не описывает проект.

## Рекомендуемый порядок следующих задач

1. Зафиксировать поддерживаемую версию Python, очистить/закрепить зависимости и добиться воспроизводимой сборки образов.
2. Добавить безопасный `APP_ENV=demo/test` и валидируемую конфигурацию с явным запретом demo-адаптеров в production.
3. Добавить PostgreSQL в локальный Compose, healthchecks и применить Alembic к чистой отдельной БД; сверить migration history с production перед любыми изменениями.
4. Реализовать изолированные demo-адаптеры SMS, storage, push и payments; исключить реальные вызовы из тестов и scheduler из demo.
5. Добавить вымышленные идемпотентные seed-данные.
6. Добавить тестовую инфраструктуру и контрактные/integration тесты пути registration → profile/photo → feed → like/pass → match → chat → text → demo subscription.
7. После стабилизации backend проверить контракты и Socket.IO events с Flutter-клиентом.
8. Заменить boilerplate README инструкцией покупателя: prerequisites, `.env.example`, migrations, seed, launch, smoke и backup/restore.

## Совместимость этого аудита

API-контракты, Socket.IO events, модели/схема БД, переменные окружения, Docker Compose и требования к Flutter-клиенту не изменялись. Добавлена только документация baseline и постоянные инструкции для следующих задач.

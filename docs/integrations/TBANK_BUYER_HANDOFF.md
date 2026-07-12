# Т-Банк: руководство по передаче и production checklist

Актуально для backend commit `8b0e46a` и контракта Subscription API v1 на 2026-07-13. Это руководство не содержит банковских ключей и не заменяет договор, настройки терминала или требования онлайн-кассы.

## 1. Архитектура платежа

1. Flutter получает тарифы с backend и отправляет только `subscription_id` и `Idempotency-Key`.
2. Backend читает цену и срок из БД, создаёт Transaction и вызывает Т-Банк `POST /v2/Init`.
3. Flutter открывает полученный PaymentURL во внешнем браузере.
4. Т-Банк отправляет `AUTHORIZED`/`CONFIRMED` и другие статусы на публичный webhook.
5. Backend до обработки проверяет Token, TerminalKey, PaymentId, OrderId и Amount.
6. Только `CONFIRMED` переводит внутренний платёж в `succeeded` и идемпотентно выдаёт подписку.
7. Flutter получает результат через status endpoint. SuccessURL и FailURL только возвращают пользователя и никогда не подтверждают оплату.

Канонический внутренний API описан в `docs/integrations/TBANK_SUBSCRIPTION_PLAN.md`; OpenAPI backend является источником истины.

## 2. Переменные окружения

| Переменная | Обязательность | Назначение |
|---|---|---|
| `APP_ENV` | всегда | `demo`, `development`, `production`; банковский test terminal запускают не в `demo` |
| `TBANK_TERMINAL_KEY` | production/test terminal | TerminalKey из кабинета Т-Бизнес |
| `TBANK_TERMINAL_PASSWORD` | production/test terminal | пароль терминала, только secret storage |
| `TBANK_API_BASE_URL` | рекомендуется явно | `https://securepay.tinkoff.ru/v2` и для DEMO-, и для production-терминала |
| `TBANK_NOTIFICATION_URL` | production/test terminal | публичный HTTPS URL `/subscriptions/webhooks/tbank` |
| `TBANK_SUCCESS_URL` | production/test terminal | HTTPS redirect после успешной формы; не источник статуса |
| `TBANK_FAIL_URL` | production/test terminal | HTTPS redirect после неуспешной формы; не источник статуса |
| `TBANK_RECURRENT_ENABLED` | всегда | `false` до отдельного согласованного запуска сохранённых реквизитов |
| `TBANK_HTTP_TIMEOUT_SECONDS` | опционально | таймаут Init, по умолчанию 10 секунд |
| `DATABASE_URL`, `ASYNC_DATABASE_URL`, `SECRET_KEY` | production | основные backend secrets/config |
| `ENVIRONMENT`, `ALEMBIC_PROD_URL` | миграции | явный выбор production БД для Alembic |

Legacy `TBANK_KASSA_TERMINAL` и `TBANK_KASSA_PASSWORD` временно читаются как aliases. Новый deployment должен использовать только канонические имена.

Не помещайте значения в Docker image, Git, Flutter dart-defines, CI output или команды shell. Используйте secret manager платформы и ограничьте доступ production-процессу.

## 3. Режимы

### Demo

`APP_ENV=demo`. Используется локальный deterministic provider без сетевого обращения к банку. Checkout создаёт реальную локальную Transaction и проходит тот же state/entitlement path. Demo endpoints доступны, реальные ключи не нужны.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

После healthchecks можно запустить `python -m scripts.seed_demo`. Не публикуйте demo backend в интернет и не используйте demo defaults в production.

### Тестовый терминал Т-Банка

Используйте выданный TerminalKey с суффиксом `DEMO`, его пароль и обычный endpoint `https://securepay.tinkoff.ru/v2`. Плановая конфигурация — `APP_ENV=development`, реальные публичные HTTPS callback URL и отдельная тестовая БД. `APP_ENV=demo` здесь не подходит: он намеренно блокирует внешнего провайдера. До запуска обязательно закройте legacy scheduler/init blockers из раздела 11: текущий non-demo runtime небезопасен для банковского терминала.

В кабинете терминала тип платежа должен совпадать с Init. Текущая интеграция рассчитана на одностадийную оплату `PayType=O`: entitlement выдаётся на `CONFIRMED`. Пройдите группы тестов «Общие» и «Формирование чека». «Автоплатежи» проходите только после отдельного подключения recurring и согласия пользователя.

### Production

`APP_ENV=production` включает fail-fast обязательных секретов. Используйте отдельные production TerminalKey/Password, production БД и HTTPS callbacks. Само значение `TBANK_RECURRENT_ENABLED=false` пока недостаточно: legacy scheduler не читает этот flag. Production запуск запрещён до устранения blockers из раздела 11.

## 4. NotificationURL, SuccessURL и FailURL

Рекомендуемые значения:

```text
TBANK_NOTIFICATION_URL=https://api.example.com/subscriptions/webhooks/tbank
TBANK_SUCCESS_URL=https://app.example.com/payment/return
TBANK_FAIL_URL=https://app.example.com/payment/return
```

- NotificationURL должен быть доступен банку по HTTPS, принимать POST и отвечать `200` с точным plain-text телом `OK` после durable обработки.
- Для HTTPS уведомлений используйте стандартный порт 443, корректную цепочку сертификатов и безусловную маршрутизацию к main API.
- Не защищайте webhook пользовательским Bearer token. Его аутентификация — банковский Token плюс сверка локальной операции.
- Redirect URL не должен менять Transaction или UserSubscription. Он может только открыть приложение/страницу и инициировать запрос status endpoint.
- При отсутствии `OK` банк повторяет уведомления, поэтому deduplication и monotonic transitions обязательны.

## 5. Init и фискализация

Т-Банк принимает Amount в копейках; он должен совпадать с суммой `Receipt.Items[].Amount`. OrderId должен быть уникальным и укладываться в лимит банка. Receipt обязателен, если к терминалу подключена онлайн-касса.

До production владелец бизнеса и специалист по кассе должны утвердить:

- `Taxation` организации;
- `Tax` для подписки;
- `PaymentMethod` (обычно зависит от момента оказания услуги);
- `PaymentObject` (для подписки обычно рассматривается `service`, но решение юридическое/фискальное);
- название позиции и правила чеков при возврате.

Не копируйте примерные налоговые значения из demo в production без подтверждения бухгалтера или оператора кассы.

## 6. Статусы и выдача доступа

| Банк | Внутренний статус | Действие |
|---|---|---|
| `NEW`, `FORM_SHOWED` | `pending` | ждать |
| `AUTHORIZING`, `3DS_CHECKING`, `3DS_CHECKED`, `AUTHORIZED`, `CONFIRMING` | `processing` | не выдавать доступ |
| `CONFIRMED` | `succeeded` | идемпотентно активировать один раз |
| `REJECTED`, `AUTH_FAIL`, `DEADLINE_EXPIRED`, `ATTEMPTS_EXPIRED` | `failed` | не активировать |
| `CANCELED`, `REVERSED`, `PARTIAL_REVERSED` | `canceled` | не активировать |
| `REFUNDING`, `ASYNC_REFUNDING` | `processing` | ждать terminal refund |
| `PARTIAL_REFUNDED` | `partially_refunded` | применить согласованную бизнес-политику |
| `REFUNDED` | `refunded` | применить согласованную compensating policy |

`AUTHORIZED` может содержать RebillId/CardId, но при двухстадийной схеме не означает окончательное списание. Текущая entitlement-логика ориентирована на `CONFIRMED`.

## 7. Webhook и идемпотентность

Token проверяется по правилам Т-Банка: исключить `Token` и вложенные объекты, добавить Password, отсортировать root scalar keys, конкатенировать значения и вычислить SHA-256 UTF-8. Сравнение выполняется constant-time.

После подписи проверяются TerminalKey, локальные PaymentId/OrderId/Amount и допустимость перехода. Webhook event имеет fingerprint; Transaction блокируется на обновление; `subscription_activated_at` и связь entitlement с source transaction не позволяют повторно начислить срок. Повторный или устаревший корректный webhook отвечает `OK`, но не меняет срок.

Мониторинг должен различать invalid token/terminal, неизвестную операцию, mismatch суммы, provider timeout, повторное событие и успешную активацию — без полного payload.

## 8. RebillId и рекуррентные платежи

Канонический subscription flow умеет принять и сохранить RebillId/CardId из подписанного webhook, но безопасные автоматические Charge, retry, pre-charge notification и billing history не входят в текущий релиз.

Для сохранения реквизитов родительский card payment требует `Recurrent=Y`, `CustomerKey` и корректный `OperationInitiatorType`; дочерний MIT recurring использует сохранённый RebillId и тип `R`. Перед включением нужны договорённость с банком, явное согласие пользователя, политика отмены, безопасное хранение идентификаторов и отдельная реализация Charge.

В репозитории остаётся legacy `common/utils/scheduler.py`, который вне demo ставит `auto_renew_subscriptions` в расписание независимо от `TBANK_RECURRENT_ENABLED`, вызывает старый Charge path и выводит RebillId в лог. Это не часть принятой архитектуры и P0 blocker для любого non-demo запуска. До remediation разрешён только `APP_ENV=demo`; недостаточно просто установить feature flag в `false`.

## 9. Миграции

Активная цепочка задана `version_locations = alembic/current_versions`:

```text
5c0b937bc038 -> a13f7c9d2e10 -> b24e8d0f3a21 (head)
```

Каталог `alembic/versions` — только архив старой неполной истории. Для новой БД:

```powershell
$env:ENVIRONMENT = 'prod'
$env:ALEMBIC_PROD_URL = '<secret database URL>'
alembic upgrade head
alembic current
alembic check
```

Перед применением сделайте backup и проверьте upgrade на копии production БД. Не выполняйте downgrade платежных таблиц после приёма реальных операций без отдельного плана восстановления.

## 10. Логи и безопасность

- Не логировать Password, Token, PAN, ExpDate, CardId, RebillId, телефон, Receipt, полный webhook/Init body и query PaymentURL.
- Логировать request/order/payment correlation ids, внутренний status, safe error code и длительность.
- Не возвращать банковские secrets в API и Flutter.
- Ограничить webhook body size, rate limit и timeout; IP allowlist использовать только как дополнительный слой, не вместо Token.
- Настроить TLS, WAF/reverse proxy, backup БД, ротацию secrets и алерты на повторные ошибки webhook.
- Репозиторный filename/content scan на 2026-07-13 не обнаружил отслеживаемых `.env`, private key/keystore или явных банковских secrets. Локальные игнорируемые файлы не являются частью поставки и должны быть удалены из передаваемого архива.

## 11. Обязательные blockers до test-terminal и production

1. Удалить либо полностью feature-gate legacy `auto_renew_subscriptions` и Charge path; expiry maintenance отделить от billing scheduler. Удалить логирование RebillId и добавить тест, что при выключенном recurring нет банковской сети.
2. Удалить или закрыть legacy `POST /subscriptions/init_payment`: endpoint принимает `amount`, OrderId и CustomerKey от клиента и обходит canonical server-priced checkout. После подтверждения отсутствия потребителей вернуть `410` на переходный период либо удалить route; добавить compatibility note и security test.
3. Удалить неиспользуемые Flutter `SubscriptionHttp`, `PaymentService` и `SubscriptionServices`, которые всё ещё содержат вызов legacy init endpoint и прямое legacy поведение.
4. Закрыть legacy Flutter logging: ряд старых network classes печатает полные response bodies, включая auth refresh response. Перевести их на `SafeApiLogInterceptor` или удалить вместе с неиспользуемым кодом.
5. После исправлений повторить весь SUB-05 E2E, test-terminal сценарии и repository secret scan.

Пока эти пункты не выполнены, статус поставки: **demo ready, non-demo blocked**.

## 12. Production checklist

- [ ] Подписан договор интернет-эквайринга, магазин и терминал созданы в Т-Бизнес.
- [ ] Юридические документы, оферта, политика возвратов и согласие на recurring утверждены.
- [ ] Онлайн-касса подключена; Taxation/Tax/PaymentMethod/PaymentObject подтверждены.
- [ ] DEMO terminal прошёл обязательные тест-кейсы и чеки.
- [ ] Production secrets загружены в secret manager и не присутствуют в Git/образе/Flutter.
- [ ] `APP_ENV=production`, production DB и canonical `TBANK_TERMINAL_*` настроены.
- [ ] NotificationURL доступен по HTTPS:443 и возвращает точный `OK`.
- [ ] SuccessURL/FailURL не активируют подписку.
- [ ] `alembic current` показывает `b24e8d0f3a21`; `alembic check` чист.
- [ ] Проверены сумма, валюта, уникальность OrderId, Init timeout и provider errors.
- [ ] Проверены AUTHORIZED + CONFIRMED, REJECTED, cancel, duplicate и out-of-order webhook.
- [ ] Настроены redacted logs, метрики, алерты, backup/restore и reconciliation runbook.
- [ ] Все blockers раздела 11 закрыты тестами; legacy scheduler/init client недостижимы.
- [ ] `TBANK_RECURRENT_ENABLED=false`, если отдельный recurring-релиз не принят; тест подтверждает отсутствие Charge network calls.
- [ ] Проведён малый реальный платёж, проверены чек, webhook, entitlement и возврат по согласованной процедуре.

## 13. Готовность функций

| Готово | Спроектировано, но не включено | Требуется покупателю |
|---|---|---|
| тарифы из БД | автоматический MIT recurring | собственные TerminalKey/Password |
| checkout и банковская форма | scheduler и Charge retry | HTTPS домены и NotificationURL |
| Token и verified webhook | уведомление перед списанием | договор, магазин и terminal settings |
| идемпотентная активация | billing history UI | оферта и политика возвратов |
| status/active/cancel | refunds UI и автоматическая entitlement policy | онлайн-касса и фискальные параметры |
| demo flow | test-terminal flow после закрытия blockers | monitoring и incident ownership |

## 14. Проверки перед передачей

```powershell
python -m pip check
python -m compileall -q admin_app common main_app push_app socket_app
python -m pytest
python -m ruff check tests/test_tbank_client.py tests/smoke/test_subscription_*.py
alembic current
alembic check
```

Последний SUB-05 прогон: 26 backend tests passed; duplicate webhook и сохранение оплаченного срока проверены E2E. Эти тесты не делают legacy non-demo scheduler безопасным — blocker проверяется отдельно.

## Официальные источники

- [Начало работы](https://developer.tbank.ru/eacq/intro)
- [Init](https://developer.tbank.ru/eacq/api/init)
- [Уведомления и Token](https://developer.tbank.ru/eacq/intro/developer/notification)
- [Тест-кейсы](https://developer.tbank.ru/eacq/intro/errors/test-cases)
- [Безопасность](https://developer.tbank.ru/eacq/intro/security)
- [Платежи по сохранённым реквизитам](https://developer.tbank.ru/eacq/scenarios/payments/PCI_DSS/autopay/)

# План интеграции подписок и Т-Банка

Статус: проектирование; production-код не изменен. Проверено 2026-07-12. Backend OpenAPI после реализации — источник истины. Flutter-копия контракта: `swipe_mobile_re/docs/contracts/SUBSCRIPTION_API.md`.

## 1. Текущее состояние backend

`Subscription`: `id`, `name`, `price: Float`, `duration`, `features`, `is_active`, `renewable`. `UserSubscription`: user/tariff, `start_date`, `end_date`, `is_active`, `next_billing_date`, `renewable`. `Transaction`: user/tariff, `amount: Float`, unique `order_number`/`payment_id`, `payment_url`, string `status`, `card_id`, `rebill_id`. `User.is_subscription` дублирует entitlement без единого механизма синхронизации.

Фактические endpoints:

| Метод | URL | Состояние |
|---|---|---|
| GET | `/subscriptions/` | Auth; отдает все тарифы, включая inactive; response DTO теряет `renewable`. |
| GET | `/subscriptions/active` | Auth; либо `{subscription_id,end_date}`, либо `{message}` с 200. |
| POST | `/subscriptions/cancel` | Auth; `renewable=false` у первой активной записи. |
| POST | `/subscriptions/promo_activate` | Auth; hard-coded plan 999 и 30 дней. |
| POST | `/subscriptions/webhook/tinkoff` | Без auth; Token не проверяет; JSON-ответ вместо `OK`. |
| POST | `/subscriptions/init_payment` | Auth; raw JSON; Init банка; доверяет полям клиента. |

Admin read-only: `/admin/subscriptions/`, `/admin/transactions/`, `/admin/user_subscriptions/`; последний ошибочно использует DTO тарифа для `UserSubscription`. Flutter вызывает отсутствующий `/subscriptions/activate_subscription`.

`init_payment` принимает `orderId`, `amount`, `customerKey`, `phone`, `subscriptionId`, вычисляет копейки из клиентского `double`, всегда передает `Recurrent=Y`, `PayType=O`, hard-coded receipt. В demo возвращает `demo://payment/success`, не создавая transaction. В остальных режимах transaction создается лишь после Init.

`generate_init_token` вручную подписывает фиксированный набор. `generate_webhook_token` применяется к GetState и подписывает только Password/PaymentId/TerminalKey. Оба расходятся с универсальным алгоритмом банка. `generate_token` незавершен и ничего не возвращает. `GetState` не подключен к пользовательскому API.

`STATUS_HANDLERS` дублирует обработчики. Только `CONFIRMED` активирует/продлевает подписку. `RebillId` сохраняется на `CONFIRMED`, хотя банк отдает его родительской операции на `AUTHORIZED`. «Автоплатеж» определяется через `order_number.startswith(subscription_id)`, реального `Charge` нет.

Env: `APP_ENV=demo|development|production`, `TBANK_KASSA_TERMINAL`, `TBANK_KASSA_PASSWORD`. Отдельного test режима/URL/timeout/return URLs нет. Специализированных payment tests нет: demo test проверяет только отсутствие сети для GetState, smoke — список тарифов. Alembic имеет старую историю в `versions` и отдельный baseline в `current_versions`; фактический production head неизвестен.

## 2. Текущее состояние Flutter

`SubscriptionScreen` полностью статический: два USD-тарифа, `Continue -> _noop`; loading/error/empty/payment states отсутствуют. Legacy `SubscriptionHttp -> SubscriptionService -> PaymentService` экраном не используется, Riverpod providers/controllers нет. Используется отдельный Dio/старый interceptor вместо общего `ApiClient`.

Init отправляет order, amount, customer key и phone. Activation вызывает отсутствующий endpoint. `PaymentService` вызывает MethodChannel `com.example.swiper/payment`, но Android/iOS handler не найден. `url_launcher`/app-link package отсутствуют; Android manifest имеет только launcher intent; route guard отсутствует. Профиль после оплаты не обновляется.

Модели ожидают `price: double`, `duration`, non-null `features`, optional `renewable`; active model — только id/end date. Subscription/payment тестов нет. Общий `APP_ENV`/`DEMO_MODE` существует, но subscription stack его не использует.

## 3. Найденные проблемы

Критические:

- цена, order/customer/phone доверяются Flutter; тариф/сумма не сверяются с БД и webhook;
- webhook Token и TerminalKey не проверяются; ответ не соответствует требуемому plain-text `OK`;
- activation не защищена отдельным уникальным effect key: гонка/повторная цепочка статусов может повторно начислить срок;
- client-driven activation небезопасна и endpoint отсутствует;
- `Float` для денег;
- SuccessURL-like demo URI имитирует успех без подтверждения backend.

Высокие:

- неверный алгоритм Token; webhook DTO отбрасывает `RebillId` и требует слишком жесткий набор полей;
- произвольные/устаревшие статусы могут перезаписать новые, полной state machine нет;
- sync `requests` внутри async endpoint, без timeout;
- общий `except Exception` превращает собственные HTTPException в 500;
- refund не корректирует entitlement по определенной policy;
- `user` может быть null в `CONFIRMED`, затем используется `user.id`;
- Flutter логирует payment data/ответы; закомментированный полный webhook log нельзя включать (PAN/CardId/RebillId/PII).

Мертвое/недостижимое: незавершенный `generate_token`, неиспользуемый GetState path, UI-неподключенные service/MethodChannel/PaymentResult, несуществующий activation endpoint, эвристика автоплатежа. Неиспользуемые imports `hmac/json/uuid` подтверждают незавершенный код.

## 4. Целевой пользовательский сценарий

1. Flutter получает active plans.
2. Пользователь выбирает plan; клиент отправляет только `subscription_id` и Idempotency-Key.
3. Backend берет цену/валюту из БД, создает локальный order/transaction и вызывает Init.
4. Flutter открывает внешний `payment_url`; карта вводится только у банка.
5. Redirect/app link лишь возвращает на pending screen и запускает refresh.
6. Backend проверяет webhook Token, terminal/order/payment/amount и переход; атомарно обновляет transaction и ровно один раз выдает entitlement; отвечает `OK`.
7. Flutter poll-ит backend с backoff; при `succeeded` обновляет active subscription и profile.
8. Cancel отключает только будущее renewal, не оплаченный срок.

## 5. Целевая архитектура

- catalog service (plans/server price);
- checkout service (local-first order + idempotency);
- единый `TBankSigner` и typed client Init/GetState с timeout;
- payment state service и reconciliation;
- entitlement service с unique `source_transaction_id`;
- synchronous verified webhook + transactional outbox для вторичных действий;
- Flutter: общий `ApiClient` -> repository -> Riverpod controller -> external URL launcher; app link только refresh trigger.

## 6. Точный внутренний API-контракт v1

JSON `snake_case`, время UTC ISO-8601, деньги integer minor units, валюта ISO 4217. User endpoints требуют Bearer auth.

### GET `/subscriptions`

```json
{"subscriptions":[{"id":1,"name":"Premium 1 month","description":"Premium access for 30 days","price_minor":49900,"currency":"RUB","duration_days":30,"is_active":true,"renewable":false}]}
```

Только active. `/subscriptions/` временно остается deprecated alias.

### POST `/subscriptions/checkout`

Обязателен `Idempotency-Key: <UUID>`.

```json
{"subscription_id":1}
```

201 впервые, 200 replay:

```json
{"order_id":"sub_42_20260712_01J...","payment_id":"1234567890","payment_url":"https://securepay.tinkoff.ru/...","status":"pending","amount_minor":49900,"currency":"RUB","expires_at":"2026-07-12T19:30:00Z"}
```

Backend генерирует amount/order/customer. `payment_id`, `payment_url`, `expires_at` nullable. Тот же ключ + другой body: 409.

### GET `/subscriptions/payments/{order_id}`

```json
{"order_id":"sub_42_20260712_01J...","payment_id":"1234567890","status":"succeeded","subscription_activated":true,"subscription":{"subscription_id":1,"name":"Premium 1 month","start_at":"2026-07-12T19:05:00Z","end_at":"2026-08-11T19:05:00Z","renewable":false},"failure_code":null,"failure_message":null,"updated_at":"2026-07-12T19:05:01Z"}
```

Только owner; чужой order не раскрывается. Nullable: payment/subscription/failure fields.

### GET `/subscriptions/active`

Всегда `{"subscription":null}` либо тот же subscription object.

### POST `/subscriptions/cancel`

Без body, идемпотентно:

```json
{"subscription":{"subscription_id":1,"name":"Premium 1 month","start_at":"2026-07-12T19:05:00Z","end_at":"2026-08-11T19:05:00Z","renewable":false}}
```

### POST `/subscriptions/webhooks/tbank`

Raw JSON банка; Token проверяется до business parsing. Valid processed/duplicate/stale: HTTP 200 `text/plain`, body `OK`. Invalid Token/terminal: 403 без `OK`; malformed: 400. Старый `/webhook/tinkoff` — только временный alias с теми же проверками.

Error envelope:

```json
{"error":{"code":"subscription_not_found","message":"Subscription is not available","retryable":false,"request_id":"01J..."}}
```

Коды: `subscription_not_found` 404, `subscription_inactive` 409, `checkout_already_pending` 409, `idempotency_conflict` 409, `payment_provider_unavailable` 503, `payment_initialization_failed` 502, `payment_not_found` 404, `unauthorized` 401, `validation_error` 422.

## 7. Pydantic DTO

```python
Currency = Literal["RUB"]
PaymentStatus = Literal["pending", "requires_action", "processing", "succeeded", "failed", "canceled", "refunded", "partially_refunded"]

class PlanDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; name: str; description: str | None = None
    price_minor: int = Field(gt=0); currency: Currency
    duration_days: int = Field(gt=0); is_active: bool; renewable: bool
class PlansResponse(BaseModel): subscriptions: list[PlanDto]
class CheckoutRequest(BaseModel): subscription_id: int = Field(gt=0)
class CheckoutResponse(BaseModel):
    order_id: str; payment_id: str | None; payment_url: HttpUrl | None
    status: PaymentStatus; amount_minor: int; currency: Currency
    expires_at: datetime | None
class ActiveSubscriptionDto(BaseModel):
    subscription_id: int; name: str; start_at: datetime; end_at: datetime; renewable: bool
class ActiveSubscriptionResponse(BaseModel): subscription: ActiveSubscriptionDto | None
class PaymentStatusResponse(BaseModel):
    order_id: str; payment_id: str | None; status: PaymentStatus
    subscription_activated: bool; subscription: ActiveSubscriptionDto | None
    failure_code: str | None; failure_message: str | None; updated_at: datetime
```

Webhook typed model разрешает documented optional primitives (`RebillId`, `CardId`, `CustomerKey`, etc.), но Token считается из исходного raw map.

## 8. Dart-модели

```dart
enum PaymentStatus { pending, requiresAction, processing, succeeded, failed, canceled, refunded, partiallyRefunded }
class SubscriptionPlan { final int id, priceMinor, durationDays; final String name, currency; final String? description; final bool isActive, renewable; }
class CheckoutRequest { final int subscriptionId; Map<String,dynamic> toJson()=>{'subscription_id':subscriptionId}; }
class CheckoutResponse { final String orderId; final String? paymentId; final Uri? paymentUrl; final PaymentStatus status; final int amountMinor; final String currency; final DateTime? expiresAt; }
class ActiveSubscription { final int subscriptionId; final String name; final DateTime startAt, endAt; final bool renewable; }
class PaymentStatusResponse { final String orderId; final String? paymentId; final PaymentStatus status; final bool subscriptionActivated; final ActiveSubscription? subscription; final String? failureCode, failureMessage; final DateTime updatedAt; }
```

Парсер reject-ит unknown statuses/types/URL/dates. Цена форматируется из minor units и не отправляется обратно.

## 9. Банковские статусы

| T-Банк | Internal | Эффект |
|---|---|---|
| `NEW`, `FORM_SHOWED` | pending | status only |
| `AUTHORIZING`, `3DS_CHECKING`, `3DS_CHECKED`, `CONFIRMING` | processing | status only |
| `AUTHORIZED` | processing | сохранить RebillId/CardId; не выдавать услугу при two-stage |
| `CONFIRMED` | succeeded | выдать entitlement ровно один раз |
| `REJECTED`, `AUTH_FAIL`, `DEADLINE_EXPIRED`, `ATTEMPTS_EXPIRED` | failed | safe failure code |
| `CANCELED`, `REVERSED`, `PARTIAL_REVERSED` | canceled | не активировать |
| `REFUNDING`, `ASYNC_REFUNDING` | processing | ждать terminal refund |
| `PARTIAL_REFUNDED` | partially_refunded | business/manual policy |
| `REFUNDED` | refunded | compensating policy |
| unknown signed | unchanged | audit + reconciliation; `OK` |

## 10. Схема состояний

```text
created -> init_pending -> pending/requires_action -> processing -> succeeded
  |            |                   |                    |-> failed/canceled
  |            -> init_failed      -> failed
  -> canceled
succeeded -> partially_refunded -> refunded
succeeded -> refunded
```

Переходы монотонны: `succeeded` нельзя заменить старым pending/failed; provider status хранится отдельно.

## 11. Изменения моделей БД

- `subscriptions`: `price_minor BIGINT CHECK >0`, `currency CHAR(3)`, `duration_days`, `description`; legacy Float columns оставить на transition.
- `transactions`: nullable string `payment_id`, `amount_minor`, currency, internal/provider status, safe error fields, idempotency key/fingerprint, expires/confirmed/updated/activated timestamps, recurrent flag/parent. Unique `(user_id,idempotency_key)`, order, partial provider payment id.
- `user_subscriptions`: unique nullable `source_transaction_id`, UTC timestamps; определить правило максимум одной active premium entitlement на user.
- `payment_webhook_events`: unique provider/payment/status/fingerprint, received/processed/result; raw payload не хранить либо redacted/encrypted.
- Будущий `billing_mandates/payment_methods`: encrypted RebillId + consent/status. Реальный recurrent Charge вне этапа.

## 12. Миграции

1. Определить реально примененный production head и свести `versions/current_versions` к одной согласованной цепочке.
2. Additive migration новых columns/constraints/indexes.
3. Backfill `round(price*100)`, `round(amount*100)` с отчетом неоднозначностей; normalize statuses.
4. Добавить/source-link entitlement только там, где связь доказуема.
5. После переключения и проверки — отдельная cleanup migration Float/legacy fields; не совмещать удаление с additive шагом.

## 13. Переменные окружения

```text
APP_ENV=demo|test|development|production
TBANK_TERMINAL_KEY=
TBANK_TERMINAL_PASSWORD=
TBANK_API_BASE_URL=https://securepay.tinkoff.ru/v2
TBANK_NOTIFICATION_URL=https://api.example/subscriptions/webhooks/tbank
TBANK_SUCCESS_URL=https://app.example/payment/return
TBANK_FAIL_URL=https://app.example/payment/return
TBANK_PAY_TYPE=O
TBANK_HTTP_TIMEOUT_SECONDS=10
TBANK_ENABLE_SAVED_CREDENTIALS=false
PAYMENT_URL_TTL_MINUTES=20
```

Старые env имена можно временно читать с warning. Test DEMO terminal использует тот же `/v2`; demo не содержит credentials и не делает сеть.

## 14. Безопасность

Token: исключить `Token` и nested objects/arrays, добавить `Password`, сортировать root primitive keys, конкатенировать values, SHA-256 UTF-8. Webhook сравнивать `hmac.compare_digest`. Затем проверять terminal/order/payment/amount/owner/transition. SuccessURL не подтверждает платеж. HTTPS, body/rate limits, redacted structured logs. Не логировать/возвращать Password, Token, PAN, phone, CardId/RebillId, receipt, полный payload или PaymentURL query. IP allowlist — только дополнительный слой к Token.

## 15. Идемпотентность

Checkout: локальная unique запись создается до банка; fingerprint фиксирует tariff. Replay возвращает тот же order; конфликт — 409; concurrency закрывается constraint/row lock.

Webhook: verify raw Token; `SELECT FOR UPDATE`; проверить invariants; unique event; разрешенный transition; entitlement insert/update с unique `source_transaction_id`; отметить activation; commit; затем `OK`. Duplicate не меняет даты. Никакой background activation до durable commit. Reconciliation GetState использует тот же state service.

## 16. Demo/test/production

- demo: deterministic fake provider, но создает настоящую local transaction и проходит тот же state/entitlement service; no network;
- test: DEMO terminal, тот же `https://securepay.tinkoff.ru/v2`, публичный HTTPS webhook и официальные test cases; saved credentials банк включает отдельно;
- development: fake по умолчанию, реальный test provider только opt-in;
- production: mandatory secrets/HTTPS/non-local, demo forbidden, saved credentials default false.

## 17. Backend-тесты

Golden Token (Init/GetState/webhook, optional/null/nested/order); exact `OK`; invalid token/terminal/order/payment/amount; duplicate/concurrent/out-of-order/unknown statuses; RebillId on AUTHORIZED; CONFIRMED twice grants once; no activation on redirect/AUTHORIZED/failure; server price; inactive tariff; checkout replay/conflict/concurrency; provider timeout; safe logs; state/refund table; demo no-network shared flow; DTO/OpenAPI errors; isolated DB; Alembic single head/clean upgrade.

## 18. Flutter-тесты

Model parsing nullable/malformed/all statuses; repository exact URL/body/header (only subscription id); controller plans loading/data/empty/error, checkout/launch/poll/resume/success/failure/cancel/timeout; one checkout/timer; widget states/demo label; SuccessURL alone never succeeds; profile refresh only after backend success; URL launch failure; app-link manifest tests if links added.

## 19. Ручной E2E

Demo: auth -> dynamic RUB plans -> double tap creates one order -> return remains pending -> fake provider confirm -> backend succeeded -> active/profile refresh -> duplicate event does not extend. Затем failed/canceled/offline/resume/invalid URL. В test terminal пройти official general/autopayment (только если enabled)/receipt cases, проверить `OK`, AUTHORIZED+CONFIRMED, сумму/Token, единственный entitlement и отсутствие secrets в логах.

## 20. Порядок задач

Backend: (1) migration head + entitlement/refund/fiscal decisions; (2) additive schema/domain DTO; (3) signer/client tests; (4) OpenAPI + aliases; (5) idempotent checkout/server price; (6) verified webhook/state/atomic entitlement; (7) demo/reconciliation/tests; (8) отдельная будущая задача consent/payment methods/scheduler/Charge.

Flutter — только после backend OpenAPI: (1) models/repository на shared ApiClient; (2) Riverpod state/tests; (3) dynamic screen, external URL, polling/resume; (4) app link only refresh + profile refresh; (5) удалить legacy singleton/MethodChannel после проверки consumers; (6) format/analyze/test/debug APK/manual test.

Блокеры: фактический Alembic head; касса и корректные Taxation/Tax/item attributes; terminal stage/PayType; нужны ли saved credentials; entitlement upgrade/refund policy; публичные HTTPS URLs/app-link domain; включение MIT recurring банком.

Официальные источники: [Init](https://developer.tbank.ru/eacq/api/init), [уведомления и Token](https://developer.tbank.ru/eacq/intro/developer/notification), [GetState](https://developer.tbank.ru/eacq/api/get-state), [saved credentials](https://developer.tbank.ru/eacq/scenarios/payments/PCI_DSS/autopay/), [test cases](https://developer.tbank.ru/eacq/intro/errors/test-cases), [security](https://developer.tbank.ru/eacq/intro/security), [refunds](https://developer.tbank.ru/eacq/scenarios/cancel_confirm/).

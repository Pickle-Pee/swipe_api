from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    Request,
    Header,
    Response,
)
from psycopg2 import DataError
from sqlalchemy.exc import IntegrityError
from fastapi.responses import PlainTextResponse

from common.models import (
    User,
    Subscription,
    UserSubscription,
    Transaction,
    PaymentWebhookEvent,
)
from common.utils import (
    get_token,
    get_user_id_from_token,
    generate_init_token,
)
from common.schemas import (
    SubscriptionsResponse,
    SubscriptionPlansResponse,
    CheckoutRequest,
    CheckoutResponse,
    PaymentStatusResponse,
    ActiveSubscriptionResponse,
)
from common.services import (
    TBankClient,
    TBankClientError,
    TBankInitRequest,
    generate_tbank_token,
)
from safe_logging import mask_identifier
from config import (
    IS_DEMO,
    IS_PRODUCTION,
    SessionLocal,
    logger,
    TBANK_KASSA_TERMINAL,
    TBANK_KASSA_PASSWORD,
    TBANK_API_BASE_URL,
    TBANK_TERMINAL_KEY,
    TBANK_TERMINAL_PASSWORD,
    TBANK_NOTIFICATION_URL,
    TBANK_SUCCESS_URL,
    TBANK_FAIL_URL,
    TBANK_RECURRENT_ENABLED,
    TBANK_HTTP_TIMEOUT_SECONDS,
)
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import requests
import uuid

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions Controller"])


def _current_user(db, access_token: str) -> User:
    user_id = get_user_id_from_token(access_token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _plan_values(subscription: Subscription) -> tuple[int, int, str]:
    price_minor = subscription.price_minor
    duration_days = subscription.duration_days
    if price_minor is None and subscription.price is not None:
        price_minor = round(subscription.price * 100)
    if duration_days is None:
        duration_days = subscription.duration
    description = subscription.description or subscription.features or subscription.name
    return int(price_minor or 0), int(duration_days or 0), description


def _checkout_response(transaction: Transaction) -> dict:
    return {
        "order_id": transaction.order_id,
        "payment_id": transaction.payment_id,
        "payment_url": transaction.payment_url,
        "status": transaction.status,
        "amount_minor": transaction.amount_minor,
        "currency": transaction.currency,
        "expires_at": transaction.expires_at,
    }


def _tbank_client() -> TBankClient:
    return TBankClient(
        base_url=TBANK_API_BASE_URL,
        terminal_key=TBANK_TERMINAL_KEY,
        password=TBANK_TERMINAL_PASSWORD,
        notification_url=TBANK_NOTIFICATION_URL,
        success_url=TBANK_SUCCESS_URL,
        fail_url=TBANK_FAIL_URL,
        recurrent_enabled=TBANK_RECURRENT_ENABLED,
        timeout_seconds=TBANK_HTTP_TIMEOUT_SECONDS,
    )


BANK_STATUS_MAP = {
    "NEW": "pending",
    "FORM_SHOWED": "pending",
    "AUTHORIZING": "processing",
    "3DS_CHECKING": "processing",
    "3DS_CHECKED": "processing",
    "AUTHORIZED": "processing",
    "CONFIRMING": "processing",
    "CONFIRMED": "succeeded",
    "REJECTED": "failed",
    "AUTH_FAIL": "failed",
    "DEADLINE_EXPIRED": "failed",
    "ATTEMPTS_EXPIRED": "failed",
    "CANCELED": "canceled",
    "REVERSED": "canceled",
    "PARTIAL_REVERSED": "canceled",
    "REFUNDING": "processing",
    "ASYNC_REFUNDING": "processing",
    "PARTIAL_REFUNDED": "partially_refunded",
    "REFUNDED": "refunded",
}


def _can_transition(current: str, target: str) -> bool:
    if current == target:
        return True
    if current == "succeeded":
        return target in {"partially_refunded", "refunded"}
    if current == "partially_refunded":
        return target == "refunded"
    if current in {"failed", "canceled", "refunded"}:
        return False
    rank = {
        "created": 0,
        "pending": 1,
        "requires_action": 1,
        "processing": 2,
        "succeeded": 3,
    }
    if target in {"failed", "canceled"}:
        return True
    return rank.get(target, -1) >= rank.get(current, -1)


def _activate_subscription(db, transaction: Transaction, now: datetime) -> None:
    if transaction.subscription_activated_at is not None:
        return
    plan = (
        db.query(Subscription)
        .filter(Subscription.id == transaction.subscription_id)
        .first()
    )
    if plan is None:
        raise RuntimeError("subscription_not_found")
    _, duration_days, _ = _plan_values(plan)
    if duration_days <= 0:
        raise RuntimeError("invalid_subscription_duration")
    active = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == transaction.user_id,
            UserSubscription.subscription_id == transaction.subscription_id,
            UserSubscription.is_active.is_(True),
            UserSubscription.end_date > now,
        )
        .with_for_update()
        .first()
    )
    if active:
        active.end_date = active.end_date + timedelta(days=duration_days)
        active.next_billing_date = active.end_date if active.renewable else None
    else:
        active = UserSubscription(
            user_id=transaction.user_id,
            subscription_id=transaction.subscription_id,
            start_date=now,
            end_date=now + timedelta(days=duration_days),
            is_active=True,
            renewable=bool(plan.renewable and TBANK_RECURRENT_ENABLED),
            next_billing_date=(now + timedelta(days=duration_days))
            if plan.renewable and TBANK_RECURRENT_ENABLED
            else None,
        )
        db.add(active)
    user = db.query(User).filter(User.id == transaction.user_id).first()
    if user:
        user.is_subscription = True
    transaction.subscription_activated_at = now


def _apply_payment_status(
    db, transaction: Transaction, bank_status: str, payload: dict
) -> str:
    target = BANK_STATUS_MAP.get(bank_status)
    if target is None:
        return "ignored_unknown_status"
    if not _can_transition(transaction.status, target):
        return "ignored_stale_status"
    if payload.get("RebillId") is not None:
        transaction.rebill_id = str(payload["RebillId"])
    if payload.get("CardId") is not None:
        transaction.card_id = str(payload["CardId"])
    transaction.bank_status = bank_status
    transaction.status = target
    now = datetime.utcnow()
    if target == "succeeded":
        transaction.confirmed_at = transaction.confirmed_at or now
        _activate_subscription(db, transaction, now)
        transaction.error_code = None
        transaction.error_message = None
    elif target in {"failed", "canceled"}:
        transaction.error_code = str(payload.get("ErrorCode") or bank_status).lower()[
            :64
        ]
        transaction.error_message = "Payment was not confirmed"
    return "processed"


def _active_subscription_payload(active: UserSubscription | None) -> dict:
    if active is None:
        return {"subscription": None}
    return {
        "subscription": {
            "subscription_id": active.subscription_id,
            "name": active.subscription.name,
            "start_at": active.start_date,
            "end_at": active.end_date,
            "renewable": bool(active.renewable),
        }
    }


@router.get(
    "", response_model=SubscriptionPlansResponse, summary="Получить активные тарифы"
)
async def get_subscription_plans(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        _current_user(db, access_token)
        plans = db.query(Subscription).filter(Subscription.is_active.is_(True)).all()
        result = []
        for plan in plans:
            price_minor, duration_days, description = _plan_values(plan)
            result.append(
                {
                    "id": plan.id,
                    "name": plan.name,
                    "description": description,
                    "price_minor": price_minor,
                    "currency": plan.currency or "RUB",
                    "duration_days": duration_days,
                    "is_active": bool(plan.is_active),
                    "renewable": bool(plan.renewable),
                }
            )
        return {"subscriptions": result}


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=201,
    summary="Создать checkout",
)
async def create_checkout(
    request: CheckoutRequest,
    response: Response,
    access_token: str = Depends(get_token),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=8, max_length=64
    ),
):
    fingerprint = hashlib.sha256(
        str(request.subscription_id).encode("utf-8")
    ).hexdigest()
    with SessionLocal() as db:
        user = _current_user(db, access_token)
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency_conflict")
            response.status_code = 200
            return _checkout_response(existing)

        plan = (
            db.query(Subscription)
            .filter(Subscription.id == request.subscription_id)
            .first()
        )
        if plan is None:
            raise HTTPException(status_code=404, detail="subscription_not_found")
        if not plan.is_active:
            raise HTTPException(status_code=409, detail="subscription_inactive")
        amount_minor, duration_days, description = _plan_values(plan)
        if amount_minor <= 0 or duration_days <= 0 or (plan.currency or "RUB") != "RUB":
            raise HTTPException(status_code=409, detail="subscription_not_payable")

        order_id = f"sub_{user.id}_{uuid.uuid4().hex[:20]}"
        transaction = Transaction(
            user_id=user.id,
            subscription_id=plan.id,
            amount=amount_minor / 100,
            amount_minor=amount_minor,
            currency="RUB",
            order_id=order_id,
            payment_id=None,
            status="pending",
            bank_status="NEW" if IS_DEMO else None,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            expires_at=datetime.utcnow() + timedelta(minutes=20),
        )
        db.add(transaction)
        try:
            db.commit()
            db.refresh(transaction)
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(Transaction)
                .filter(
                    Transaction.user_id == user.id,
                    Transaction.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing and existing.request_fingerprint == fingerprint:
                response.status_code = 200
                return _checkout_response(existing)
            raise HTTPException(status_code=409, detail="idempotency_conflict")

        if IS_DEMO:
            transaction.payment_id = f"demo-{transaction.id}"
            transaction.payment_url = f"https://demo.swipe.local/payments/{order_id}"
            transaction.bank_status = "NEW"
            db.commit()
            db.refresh(transaction)
            logger.info(
                "payment_checkout_initialized operation=demo order_id=%s payment_id=%s status=pending",
                order_id,
                mask_identifier(transaction.payment_id),
            )
            return _checkout_response(transaction)

        try:
            result = _tbank_client().init_payment(
                TBankInitRequest(
                    amount_minor=amount_minor,
                    order_id=order_id,
                    description=description,
                    customer_key=str(user.id),
                )
            )
        except TBankClientError as exc:
            transaction.status = "failed"
            transaction.error_code = exc.code[:64]
            transaction.error_message = "Payment provider could not initialize payment"
            db.commit()
            logger.warning(
                "payment_checkout_init_failed order_id=%s error_code=%s retryable=%s",
                order_id,
                exc.code[:64],
                exc.retryable,
            )
            raise HTTPException(
                status_code=503 if exc.retryable else 502,
                detail="payment_provider_unavailable"
                if exc.retryable
                else "payment_initialization_failed",
            )
        transaction.payment_id = result.payment_id
        transaction.payment_url = result.payment_url
        transaction.bank_status = result.status
        db.commit()
        db.refresh(transaction)
        logger.info(
            "payment_checkout_initialized operation=init order_id=%s payment_id=%s status=%s",
            order_id,
            mask_identifier(transaction.payment_id),
            transaction.bank_status,
        )
        return _checkout_response(transaction)


@router.get(
    "/payments/{order_id}",
    response_model=PaymentStatusResponse,
    summary="Получить статус checkout",
)
async def get_checkout_status(order_id: str, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user = _current_user(db, access_token)
        transaction = (
            db.query(Transaction)
            .filter(
                Transaction.order_id == order_id,
                Transaction.user_id == user.id,
            )
            .first()
        )
        if transaction is None:
            raise HTTPException(status_code=404, detail="payment_not_found")
        active = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.user_id == user.id,
                UserSubscription.subscription_id == transaction.subscription_id,
                UserSubscription.is_active.is_(True),
                UserSubscription.end_date > datetime.utcnow(),
            )
            .first()
        )
        subscription = None
        if active:
            subscription = {
                "subscription_id": active.subscription_id,
                "name": active.subscription.name,
                "start_at": active.start_date,
                "end_at": active.end_date,
                "renewable": bool(active.renewable),
            }
        return {
            "order_id": transaction.order_id,
            "payment_id": transaction.payment_id,
            "status": transaction.status,
            "subscription_activated": active is not None,
            "subscription": subscription,
            "failure_code": transaction.error_code,
            "failure_message": transaction.error_message,
            "updated_at": transaction.updated_at,
        }


@router.post(
    "/demo/payments/{order_id}/{result}",
    response_model=PaymentStatusResponse,
    summary="Эмулировать demo-платеж",
)
async def set_demo_payment_result(
    order_id: str, result: str, access_token: str = Depends(get_token)
):
    if IS_PRODUCTION or not IS_DEMO:
        raise HTTPException(status_code=404, detail="Not found")
    if result not in {"success", "failure"}:
        raise HTTPException(status_code=422, detail="result must be success or failure")
    with SessionLocal() as db:
        user = _current_user(db, access_token)
        transaction = (
            db.query(Transaction)
            .filter(Transaction.order_id == order_id, Transaction.user_id == user.id)
            .with_for_update()
            .first()
        )
        if transaction is None:
            raise HTTPException(status_code=404, detail="payment_not_found")
        bank_status = "CONFIRMED" if result == "success" else "REJECTED"
        _apply_payment_status(
            db,
            transaction,
            bank_status,
            {"ErrorCode": "demo_rejected" if result == "failure" else "0"},
        )
        db.commit()
    return await get_checkout_status(order_id, access_token)


@router.get("/", response_model=SubscriptionsResponse, summary="Получить все подписки")
async def get_subscriptions(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        subscriptions = db.query(Subscription).all()
        return {"subscriptions": subscriptions}


@router.get(
    "/active",
    response_model=ActiveSubscriptionResponse,
    summary="Получить активную подписку",
)
async def get_active_subscription(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user = _current_user(db, access_token)
        active_subscription = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.user_id == user.id,
                UserSubscription.is_active.is_(True),
                UserSubscription.end_date > datetime.utcnow(),
            )
            .order_by(UserSubscription.end_date.desc())
            .first()
        )
        return _active_subscription_payload(active_subscription)


@router.post(
    "/cancel",
    response_model=ActiveSubscriptionResponse,
    summary="Отменить автоматическое продление",
)
async def cancel_subscription(access_token: str = Depends(get_token)):
    """
    Отключает автоматическое продление подписки пользователя.
    Подписка останется активной до наступления end_date.
    """
    with SessionLocal() as db:
        user = _current_user(db, access_token)
        active_subscription = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.user_id == user.id,
                UserSubscription.is_active.is_(True),
                UserSubscription.end_date > datetime.utcnow(),
            )
            .order_by(UserSubscription.end_date.desc())
            .first()
        )

        if active_subscription is None:
            raise HTTPException(status_code=404, detail="active_subscription_not_found")
        active_subscription.renewable = False
        active_subscription.next_billing_date = None
        db.commit()
        db.refresh(active_subscription)
        return _active_subscription_payload(active_subscription)


@router.post("/promo_activate", summary="Активировать промо-подписку бесплатно")
async def promo_activate(access_token: str = Depends(get_token)):
    """
    Активирует бесплатную промо-подписку без обращения к банку.
    """

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        # Проверяем, нет ли уже активной подписки
        active_sub = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active.is_(True),
                UserSubscription.end_date > datetime.utcnow(),
            )
            .first()
        )

        if active_sub:
            raise HTTPException(
                status_code=400, detail="У вас уже есть активная подписка."
            )

        # Ищем промо-подписку (id=999) или выдаём ошибку
        promo_sub = db.query(Subscription).filter(Subscription.id == 999).first()
        if not promo_sub:
            raise HTTPException(
                status_code=400, detail="Промо-подписка не найдена в базе (id=999)."
            )

        # Создаём новую запись UserSubscription (например, на 30 дней)
        new_user_sub = UserSubscription(
            user_id=user_id,
            subscription_id=promo_sub.id,  # 999
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),  # 30 дней промо
            is_active=True,
            renewable=False,  # Если промо не нужно продлевать
        )
        db.add(new_user_sub)

        # Проставляем пользователю флаг is_subscription = True
        user.is_subscription = True

        db.commit()  # фиксируем всё одним коммитом
        db.refresh(new_user_sub)
        db.refresh(user)

        return {
            "message": "Промо-подписка успешно активирована!",
            "subscription_id": promo_sub.id,
            "end_date": new_user_sub.end_date.isoformat(),
        }


@router.post(
    "/webhooks/tbank", response_class=PlainTextResponse, summary="Webhook Т-Банка"
)
@router.post(
    "/webhook/tinkoff",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
async def handle_tbank_webhook(request: Request):
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid_webhook_payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_webhook_payload")
    required = ("TerminalKey", "OrderId", "PaymentId", "Status", "Amount", "Token")
    if any(payload.get(field) is None for field in required):
        raise HTTPException(status_code=400, detail="invalid_webhook_payload")
    if not TBANK_TERMINAL_KEY or not TBANK_TERMINAL_PASSWORD:
        raise HTTPException(status_code=503, detail="payment_provider_not_configured")
    if not hmac.compare_digest(str(payload["TerminalKey"]), TBANK_TERMINAL_KEY):
        logger.warning("payment_webhook_rejected reason=invalid_terminal")
        raise HTTPException(status_code=403, detail="invalid_webhook_terminal")
    expected_token = generate_tbank_token(payload, TBANK_TERMINAL_PASSWORD)
    if not hmac.compare_digest(str(payload["Token"]), expected_token):
        logger.warning("payment_webhook_rejected reason=invalid_token")
        raise HTTPException(status_code=403, detail="invalid_webhook_token")

    payment_id = str(payload["PaymentId"])
    order_id = str(payload["OrderId"])
    bank_status = str(payload["Status"]).upper()
    try:
        amount_minor = int(payload["Amount"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid_webhook_amount")
    canonical = json.dumps(
        {key: value for key, value in payload.items() if key != "Token"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with SessionLocal() as db:
        duplicate = (
            db.query(PaymentWebhookEvent)
            .filter(PaymentWebhookEvent.event_fingerprint == fingerprint)
            .first()
        )
        if duplicate:
            return PlainTextResponse("OK")
        transaction = (
            db.query(Transaction)
            .filter(Transaction.payment_id == payment_id)
            .with_for_update()
            .first()
        )
        if transaction is None:
            raise HTTPException(status_code=404, detail="payment_not_found")
        if transaction.order_id != order_id:
            raise HTTPException(status_code=400, detail="order_id_mismatch")
        if transaction.amount_minor != amount_minor:
            raise HTTPException(status_code=400, detail="amount_mismatch")
        result = _apply_payment_status(db, transaction, bank_status, payload)
        now = datetime.utcnow()
        db.add(
            PaymentWebhookEvent(
                payment_id=payment_id,
                order_id=order_id,
                bank_status=bank_status,
                event_fingerprint=fingerprint,
                received_at=now,
                processed_at=now,
                result=result,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return PlainTextResponse("OK")
    logger.info(
        "payment_webhook_processed order_id=%s payment_id=%s status=%s result=%s",
        order_id,
        mask_identifier(payment_id),
        bank_status,
        result,
    )
    return PlainTextResponse("OK")


@router.post(
    "/init_payment",
    summary="Удалённый legacy endpoint оплаты",
    deprecated=True,
)
async def init_payment():
    raise HTTPException(
        status_code=410,
        detail={
            "code": "LEGACY_PAYMENT_ENDPOINT_REMOVED",
            "message": "Use POST /subscriptions/checkout",
        },
    )

    # Compatibility source is intentionally unreachable during the one-release
    # 410 window and will be deleted together with this route in the next release.
    data = await request.json()  # noqa: F821 - unreachable compatibility source
    logger.info("Payment initialization request received")

    # Проверка обязательных параметров, исключая email
    required_fields = ["orderId", "amount", "customerKey", "phone", "subscriptionId"]
    if not all(field in data and data[field] for field in required_fields):
        logger.error("Missing required parameters")
        raise HTTPException(status_code=400, detail="Missing required parameters")

    if IS_DEMO:
        return {
            "paymentId": 0,
            "paymentURL": "demo://payment/success",
            "orderId": data["orderId"],
            "amount": data["amount"],
            "description": f"Demo payment for order {data['orderId']}",
            "customerKey": data["customerKey"],
            "subscriptionId": data["subscriptionId"],
        }

    with SessionLocal() as db:
        user_id = get_user_id_from_token(
            access_token  # noqa: F821 - unreachable compatibility source
        )
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        # Получаем данные из запроса
        order_id = data.get("orderId")
        amount = data.get("amount")
        customer_key = data.get("customerKey")
        phone = data.get("phone")
        subscription_id = data.get("subscriptionId")

        # Преобразуем subscription_id в Integer
        try:
            subscription_id = int(subscription_id)
        except ValueError:
            logger.error("Legacy payment request has invalid subscription_id")
            raise HTTPException(
                status_code=400, detail="Invalid subscription_id format"
            )

    # Формируем параметры для запроса Init
    init_params = {
        "TerminalKey": TBANK_KASSA_TERMINAL,
        "Amount": int(float(amount) * 100),
        "OrderId": order_id,
        "Description": f"Оплата по заказу №{order_id}",
        "DATA": {
            "Phone": phone,
            "SubscriptionId": subscription_id,
            "UserId": customer_key,
        },
        "Receipt": {
            "Phone": phone,
            "Taxation": "osn",
            "Items": [
                {
                    "Name": "Подписка VIP",
                    "Price": int(float(amount) * 100),
                    "Quantity": 1,
                    "Amount": int(float(amount) * 100),
                    "Tax": "vat0",
                }
            ],
        },
        "CustomerKey": customer_key,
        "Recurrent": "Y",
        "PayType": "O",
    }

    try:
        token = generate_init_token(init_params, TBANK_KASSA_PASSWORD)
    except ValueError:
        logger.error("Legacy payment token generation failed")
        raise HTTPException(status_code=400, detail="Payment configuration error")

    init_params["Token"] = token

    # Отправляем запрос Init
    try:
        response = requests.post(
            "https://securepay.tinkoff.ru/v2/Init", json=init_params
        )
        response_data = response.json()
        logger.info("Payment provider response received")

        if response_data.get("Success"):
            payment_id_str = response_data.get("PaymentId")
            payment_url = response_data.get("PaymentURL", "")
            try:
                payment_id = int(payment_id_str)
            except (ValueError, TypeError):
                logger.error("Legacy Init returned an invalid PaymentId")
                raise HTTPException(
                    status_code=400, detail="Invalid PaymentId format from Tinkoff"
                )

            # Сохраняем данные в базу данных
            with SessionLocal() as db:
                new_transaction = Transaction(
                    user_id=user_id,
                    subscription_id=subscription_id,
                    amount=amount,
                    order_number=order_id,
                    payment_id=payment_id,
                    payment_url=payment_url,
                    status="INITIATED",
                    # card_id и rebill_id остаются None на данном этапе
                )
                db.add(new_transaction)
                try:
                    db.commit()
                    db.refresh(new_transaction)
                except IntegrityError:
                    db.rollback()
                    logger.error("Legacy payment transaction integrity error")
                    raise HTTPException(
                        status_code=400,
                        detail="Integrity error while saving transaction.",
                    )
                except DataError:
                    db.rollback()
                    logger.error("Legacy payment transaction data error")
                    raise HTTPException(
                        status_code=400, detail="Data error while saving transaction."
                    )
                except Exception:
                    db.rollback()
                    logger.exception("Legacy payment transaction persistence failed")
                    raise HTTPException(
                        status_code=500, detail="Internal server error."
                    )

            return {
                "paymentId": payment_id,
                "paymentURL": payment_url,
                "orderId": order_id,
                "amount": amount,
                "description": f"Оплата по заказу №{order_id}",
                "customerKey": customer_key,
                "subscriptionId": subscription_id,
            }
        else:
            error_code = response_data.get("ErrorCode", "UNKNOWN_ERROR")
            logger.error("Legacy Init rejected error_code=%s", error_code)
            raise HTTPException(
                status_code=400, detail="Failed to initialize payment"
            )
    except requests.RequestException:
        logger.exception("Legacy Init transport failed")
        raise HTTPException(
            status_code=502, detail="Failed to communicate with payment provider."
        )
    except Exception:
        logger.exception("Legacy payment initialization failed")
        raise HTTPException(status_code=500, detail="Internal server error.")

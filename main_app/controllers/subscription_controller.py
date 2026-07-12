from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    BackgroundTasks,
    Request,
    Header,
    Response,
)
from psycopg2 import DataError
from sqlalchemy.exc import IntegrityError

from common.models import User, Subscription, UserSubscription, Transaction
from common.utils import (
    get_token,
    get_user_id_from_token,
    generate_init_token,
    STATUS_HANDLERS,
)
from common.schemas import (
    SubscriptionsResponse,
    TinkoffWebhook,
    SubscriptionPlansResponse,
    CheckoutRequest,
    CheckoutResponse,
    PaymentStatusResponse,
)
from common.services import TBankClient, TBankClientError, TBankInitRequest
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
            .first()
        )
        if transaction is None:
            raise HTTPException(status_code=404, detail="payment_not_found")
        transaction.status = "succeeded" if result == "success" else "failed"
        transaction.bank_status = "CONFIRMED" if result == "success" else "REJECTED"
        transaction.confirmed_at = datetime.utcnow() if result == "success" else None
        transaction.error_code = None if result == "success" else "demo_rejected"
        transaction.error_message = (
            None if result == "success" else "Demo payment was rejected"
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


@router.get("/active", summary="Получить активную подписку")
async def get_active_subscription(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        active_subscription = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active.is_(True),
                UserSubscription.end_date > datetime.utcnow(),
            )
            .first()
        )

        if active_subscription is None:
            return {"message": "No active subscription"}

        return {
            "subscription_id": active_subscription.subscription_id,
            "end_date": active_subscription.end_date,
        }


@router.post("/cancel", summary="Отменить подписку")
async def cancel_subscription(access_token: str = Depends(get_token)):
    """
    Отключает автоматическое продление подписки пользователя.
    Подписка останется активной до наступления end_date.
    """
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        active_subscription = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active.is_(True),
                UserSubscription.end_date > datetime.utcnow(),
            )
            .first()
        )

        if active_subscription is None:
            raise HTTPException(
                status_code=400, detail="No active subscription to cancel"
            )

        active_subscription.renewable = False

        db.commit()

        return {"message": "Subscription cancellation initiated successfully"}


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


@router.post("/webhook/tinkoff", summary="Webhook для обработки платежей от Тинькофф")
async def handle_tinkoff_webhook(
    webhook: TinkoffWebhook, background_tasks: BackgroundTasks
):
    """
    Обработчик Webhook уведомлений от Тинькофф.
    """

    """
    TODO: Добавить IP тинька
    """
    # client_ip = request.client.host
    # ALLOWED_IPS = ["185.165.163.3"]
    #
    # if client_ip not in ALLOWED_IPS:
    #     logger.warning(f"Unauthorized IP address: {client_ip}")
    #     raise HTTPException(status_code=403, detail="Forbidden")

    # logger.info(f"Received webhook from {client_ip}: {webhook.dict(by_alias=True)}")

    # Обработка событий
    status = webhook.Status
    payment_id = webhook.PaymentId

    if not payment_id:
        logger.error("Webhook payload missing 'PaymentId'")
        raise HTTPException(status_code=400, detail="Missing PaymentId")

    # Получаем соответствующий обработчик для статуса
    handler = STATUS_HANDLERS.get(status)
    if handler:
        background_tasks.add_task(handler, str(payment_id), status, webhook.dict())
    else:
        logger.warning(
            f"No handler defined for status {status} for PaymentId {payment_id}"
        )

    return {"message": "Webhook received"}


@router.post("/init_payment", summary="Инициализация платежа")
async def init_payment(request: Request, access_token: str = Depends(get_token)):
    data = await request.json()
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
        user_id = get_user_id_from_token(access_token)
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
            logger.error(f"Invalid subscription_id format: {subscription_id}")
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
    except ValueError as ve:
        logger.error(f"Token generation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

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
                logger.error(f"Invalid PaymentId format: {payment_id_str}")
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
                except IntegrityError as ie:
                    db.rollback()
                    logger.error(f"Database IntegrityError: {ie}")
                    raise HTTPException(
                        status_code=400,
                        detail="Integrity error while saving transaction.",
                    )
                except DataError as de:
                    db.rollback()
                    logger.error(f"Database DataError: {de}")
                    raise HTTPException(
                        status_code=400, detail="Data error while saving transaction."
                    )
                except Exception as e:
                    db.rollback()
                    logger.exception(f"Unexpected error while saving transaction: {e}")
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
            error_message = response_data.get("Message", "Unknown error")
            logger.error(f"Tinkoff Init Error: {error_code} - {error_message}")
            raise HTTPException(
                status_code=400, detail=f"Failed to initialize payment: {error_message}"
            )
    except requests.RequestException as e:
        logger.exception(f"HTTP request to Tinkoff Init failed: {e}")
        raise HTTPException(
            status_code=502, detail="Failed to communicate with payment provider."
        )
    except Exception as e:
        logger.exception(f"Exception during payment initialization: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

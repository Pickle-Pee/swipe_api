from fastapi import HTTPException, APIRouter, Depends, BackgroundTasks, Request
from psycopg2 import DataError
from sqlalchemy.exc import IntegrityError

from common.models import User, Subscription, UserSubscription, Transaction
from common.utils import (
    get_token,
    get_user_id_from_token,
    generate_init_token,
    STATUS_HANDLERS,
)
from common.schemas import SubscriptionsResponse, TinkoffWebhook
from config import IS_DEMO, SessionLocal, logger, TBANK_KASSA_TERMINAL, TBANK_KASSA_PASSWORD
from datetime import datetime, timedelta
import requests

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions Controller"])


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

        active_subscription = db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id,
            UserSubscription.is_active == True,
            UserSubscription.end_date > datetime.utcnow()
        ).first()

        if active_subscription is None:
            return {"message": "No active subscription"}

        return {
            "subscription_id": active_subscription.subscription_id,
            "end_date": active_subscription.end_date
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

        active_subscription = db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id,
            UserSubscription.is_active == True,
            UserSubscription.end_date > datetime.utcnow()
        ).first()

        if active_subscription is None:
            raise HTTPException(status_code=400, detail="No active subscription to cancel")

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
        active_sub = db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id,
            UserSubscription.is_active == True,
            UserSubscription.end_date > datetime.utcnow()
        ).first()

        if active_sub:
            raise HTTPException(
                status_code=400,
                detail="У вас уже есть активная подписка."
            )

        # Ищем промо-подписку (id=999) или выдаём ошибку
        promo_sub = db.query(Subscription).filter(Subscription.id == 999).first()
        if not promo_sub:
            raise HTTPException(
                status_code=400,
                detail="Промо-подписка не найдена в базе (id=999)."
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
async def handle_tinkoff_webhook(webhook: TinkoffWebhook, background_tasks: BackgroundTasks):
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
        logger.warning(f"No handler defined for status {status} for PaymentId {payment_id}")

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
            raise HTTPException(status_code=400, detail="Invalid subscription_id format")

    # Формируем параметры для запроса Init
    init_params = {
        "TerminalKey": TBANK_KASSA_TERMINAL,
        "Amount": int(float(amount) * 100),
        "OrderId": order_id,
        "Description": f"Оплата по заказу №{order_id}",
        "DATA": {
            "Phone": phone,
            "SubscriptionId": subscription_id,
            "UserId": customer_key
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
                    "Tax": "vat0"
                }
            ]
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
        response = requests.post("https://securepay.tinkoff.ru/v2/Init", json=init_params)
        response_data = response.json()
        logger.info("Payment provider response received")

        if response_data.get("Success"):
            payment_id_str = response_data.get("PaymentId")
            payment_url = response_data.get("PaymentURL", "")
            try:
                payment_id = int(payment_id_str)
            except (ValueError, TypeError):
                logger.error(f"Invalid PaymentId format: {payment_id_str}")
                raise HTTPException(status_code=400, detail="Invalid PaymentId format from Tinkoff")

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
                    raise HTTPException(status_code=400, detail="Integrity error while saving transaction.")
                except DataError as de:
                    db.rollback()
                    logger.error(f"Database DataError: {de}")
                    raise HTTPException(status_code=400, detail="Data error while saving transaction.")
                except Exception as e:
                    db.rollback()
                    logger.exception(f"Unexpected error while saving transaction: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error.")

            return {
                "paymentId": payment_id,
                "paymentURL": payment_url,
                "orderId": order_id,
                "amount": amount,
                "description": f"Оплата по заказу №{order_id}",
                "customerKey": customer_key,
                "subscriptionId": subscription_id
            }
        else:
            error_code = response_data.get("ErrorCode", "UNKNOWN_ERROR")
            error_message = response_data.get("Message", "Unknown error")
            logger.error(f"Tinkoff Init Error: {error_code} - {error_message}")
            raise HTTPException(status_code=400, detail=f"Failed to initialize payment: {error_message}")
    except requests.RequestException as e:
        logger.exception(f"HTTP request to Tinkoff Init failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with payment provider.")
    except Exception as e:
        logger.exception(f"Exception during payment initialization: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

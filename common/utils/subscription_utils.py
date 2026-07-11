import hmac
import json
import uuid

import requests
from sqlalchemy.orm import Session
from common.models import User, UserSubscription, Transaction, Subscription
from config import IS_DEMO, SessionLocal, TBANK_KASSA_PASSWORD, TBANK_KASSA_TERMINAL, logger
from datetime import datetime, timedelta

import hashlib


def get_active_subscription(db: Session, user_id: int, subscription_id: int) -> UserSubscription:
    """
    Получает активную подписку пользователя для конкретного типа подписки.

    :param db: Сессия базы данных.
    :param user_id: Идентификатор пользователя.
    :param subscription_id: Идентификатор подписки.
    :return: Активная подписка или None.
    """
    return db.query(UserSubscription).filter(
        UserSubscription.user_id == user_id,
        UserSubscription.subscription_id == subscription_id,
        UserSubscription.is_active == True,
        UserSubscription.end_date > datetime.utcnow()
    ).first()


def generate_init_token(params: dict, password: str) -> str:
    """
    Генерирует Token на основе переданных параметров и пароля терминала.
    Параметры конкатенируются в определённом порядке:
    Amount, CustomerKey, Description, OrderId, Password, PayType, Recurrent, TerminalKey.
    """
    # Определяем порядок параметров
    ordered_keys = ['Amount', 'CustomerKey', 'Description', 'OrderId']

    token_str = ""
    for key in ordered_keys:
        if key in params and params[key] is not None:
            token_str += str(params[key])
        else:
            raise ValueError(f"Missing required parameter for token generation: {key}")

    # Добавляем пароль терминала
    token_str += password

    # Добавляем PayType и Recurrent
    if 'PayType' in params and params['PayType'] is not None:
        token_str += str(params['PayType'])
    else:
        raise ValueError("Missing required parameter for token generation: PayType")

    if 'Recurrent' in params and params['Recurrent'] is not None:
        token_str += str(params['Recurrent'])
    else:
        raise ValueError("Missing required parameter for token generation: Recurrent")

    # Добавляем TerminalKey
    if 'TerminalKey' in params and params['TerminalKey'] is not None:
        token_str += str(params['TerminalKey'])
    else:
        raise ValueError("Missing required parameter for token generation: TerminalKey")

    # Генерируем SHA-256 хэш
    token = hashlib.sha256(token_str.encode('utf-8')).hexdigest()

    return token


def generate_token(params: dict, password: str) -> str:
    """
    Генерирует Token на основе переданных параметров и пароля терминала.
    Параметры конкатенируются в определённом порядке:
    Amount, CustomerKey, Description, OrderId, Password, PayType, Recurrent, TerminalKey.
    """
    # Определяем порядок параметров
    ordered_keys = ['Amount', 'CustomerKey', 'Description', 'OrderId']

    token_str = ""
    for key in ordered_keys:
        if key in params and params[key] is not None:
            token_str += str(params[key])
        else:
            raise ValueError(f"Missing required parameter for token generation: {key}")


def generate_webhook_token(params: dict, password: str) -> str:
    """
    Генерирует Token для вебхука.

    Логика:
    1. Конкатенация TerminalPassword + PaymentId + TerminalKey.
    2. Генерация SHA-256 хэша.
    """
    terminal_key = params.get("TerminalKey", "")
    payment_id = params.get("PaymentId", "")

    if not terminal_key or not payment_id:
        raise ValueError("Missing required parameters for webhook token generation")

    token_str = f"{password}{payment_id}{terminal_key}"
    token = hashlib.sha256(token_str.encode('utf-8')).hexdigest()
    return token


def get_payment_info_from_tinkoff(payment_id: str):
    """
    Получает информацию о платеже из Тинькофф по PaymentId.

    :param payment_id: Идентификатор платежа.
    :return: Ответ от Тинькофф в формате JSON или None в случае ошибки.
    """
    if IS_DEMO:
        logger.info("Payment state request skipped in demo mode")
        return {"Success": True, "Status": "CONFIRMED", "PaymentId": payment_id, "Demo": True}

    url = "https://securepay.tinkoff.ru/v2/GetState"
    data = {
        "TerminalKey": TBANK_KASSA_TERMINAL,
        "PaymentId": payment_id
    }
    try:
        data["Token"] = generate_webhook_token(data, TBANK_KASSA_PASSWORD)
    except ValueError as ve:
        logger.error(f"Token generation error: {ve}")
        return None

    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get payment info from Tinkoff: {e}")
        return None


def handle_new_status(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус NEW.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_form_showed(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус FORM_SHOWED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_authorizing(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус AUTHORIZING.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_authorized(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус AUTHORIZED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_confirming(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус CONFIRMING.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_confirmed(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус CONFIRMED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    if webhook_data is None:
        logger.error("Webhook data is required for handle_confirmed")
        return

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        # Проверяем текущий статус транзакции
        if transaction.status in ['REFUNDED', 'CANCELED', 'REJECTED']:
            logger.warning(f"Transaction {transaction.order_number} has final status {transaction.status}. Skipping update.")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        # Обновляем статус транзакции
        transaction.status = status

        # Сохраняем CardId и RebillId из данных вебхука
        transaction.card_id = webhook_data.get('CardId')
        transaction.rebill_id = webhook_data.get('RebillId')

        # Проверяем, является ли транзакция автоплатежом
        if transaction.order_number.startswith(str(transaction.subscription_id)):
            # Получаем подписку пользователя
            user_subscription = db.query(UserSubscription).filter(
                UserSubscription.user_id == transaction.user_id,
                UserSubscription.subscription_id == transaction.subscription_id,
                UserSubscription.is_active == True
            ).first()

            if user_subscription:
                user_subscription.start_date = datetime.utcnow()
                user_subscription.end_date = datetime.utcnow() + timedelta(days=transaction.subscription.duration)
                user_subscription.next_billing_date = user_subscription.end_date
                logger.info(f"Обновлена подписка ID {user_subscription.id} для пользователя ID {transaction.user_id} до {user_subscription.end_date}")
            else:
                logger.warning(f"Активная подписка для пользователя ID {transaction.user_id} не найдена")
        else:
            # Обновляем флаг is_subscription для пользователя
            user = db.query(User).filter(User.id == transaction.user_id).first()
            if user:
                user.is_subscription = True

            # Получаем подписку
            subscription = db.query(Subscription).filter(Subscription.id == transaction.subscription_id).first()
            if not subscription:
                logger.error(f"Subscription with id {transaction.subscription_id} not found")
                db.rollback()
                return

            # Проверяем, есть ли у пользователя активная подписка данного типа
            existing_subscription = get_active_subscription(db, user.id, subscription.id)

            if existing_subscription:
                # Продлеваем дату окончания подписки
                existing_subscription.end_date += timedelta(days=subscription.duration)
                existing_subscription.next_billing_date = existing_subscription.end_date
                logger.info(f"Extended subscription for user {user.id} until {existing_subscription.end_date}")
            else:
                # Создаём новую подписку
                user_subscription = UserSubscription(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=subscription.duration),
                    is_active=True,
                    next_billing_date=datetime.utcnow() + timedelta(days=subscription.duration) if subscription.renewable else None,
                    renewable=subscription.renewable
                )
                db.add(user_subscription)
                logger.info(f"Created new subscription for user {user.id} until {user_subscription.end_date}")

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_refunding(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус REFUNDING.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_async_refunding(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус ASYNC_REFUNDING.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_partial_refunded(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус PARTIAL_REFUNDED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_refunded(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус REFUNDED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        # Обновляем статус транзакции
        transaction.status = status

        # Проверяем, есть ли у пользователя другие активные подписки
        user = db.query(User).filter(User.id == transaction.user_id).first()
        if user:
            active_subscriptions = db.query(UserSubscription).filter(
                UserSubscription.user_id == user.id,
                UserSubscription.is_active == True,
                UserSubscription.end_date > datetime.utcnow()
            ).all()
            if not active_subscriptions:
                user.is_subscription = False
                logger.info(f"User {user.id} has no active subscriptions. is_subscription set to False")

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")




def handle_canceled(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус CANCELED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_deadline_expired(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус DEADLINE_EXPIRED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_attempts_expired(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус ATTEMPTS_EXPIRED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_auth_fail(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус AUTH_FAIL.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        # Обновляем статус транзакции
        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")


def handle_rejected_status(payment_id: str, status: str, webhook_data: dict = None):
    """
    Обрабатывает статус REJECTED.
    """
    logger.info(f"Handling status {status} for PaymentId {payment_id}")

    with SessionLocal() as db:
        try:
            payment_id_int = int(payment_id)
        except ValueError:
            logger.error(f"Invalid PaymentId format: {payment_id}")
            return

        transaction = db.query(Transaction).filter(Transaction.payment_id == payment_id_int).first()
        if not transaction:
            logger.error(f"Transaction with PaymentId {payment_id} not found")
            return

        if transaction.status == status:
            logger.info(f"Transaction {transaction.order_number} already set to {status}")
            return

        # Обновляем статус транзакции
        transaction.status = status

        try:
            db.commit()
            logger.info(f"Transaction {transaction.order_number} set to {status}")
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to set transaction {transaction.order_number} to {status}: {e}")



STATUS_HANDLERS = {
    "NEW": handle_new_status,
    "FORM_SHOWED": handle_form_showed,
    "AUTHORIZING": handle_authorizing,
    "AUTHORIZED": handle_authorized,
    "CONFIRMING": handle_confirming,
    "CONFIRMED": handle_confirmed,
    "REFUNDING": handle_refunding,
    "ASYNC_REFUNDING": handle_async_refunding,
    "PARTIAL_REFUNDED": handle_partial_refunded,
    "REFUNDED": handle_refunded,
    "CANCELED": handle_canceled,
    "DEADLINE_EXPIRED": handle_deadline_expired,
    "ATTEMPTS_EXPIRED": handle_attempts_expired,
    "REJECTED": handle_rejected_status,
    "AUTH_FAIL": handle_auth_fail,
}

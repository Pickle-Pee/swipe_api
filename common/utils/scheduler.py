from typing import Tuple, Any

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from common.models import UserSubscription, User, Subscription, Transaction
from config import IS_DEMO, SessionLocal, logger, TBANK_KASSA_TERMINAL
from datetime import datetime, timedelta
import requests


def deactivate_expired_subscriptions():
    logger.info("Запуск проверки истекших подписок")
    utc_timezone = pytz.timezone('UTC')

    with SessionLocal() as db:
        now = utc_timezone.localize(datetime.utcnow())
        expired_subscriptions = db.query(UserSubscription).filter(
            UserSubscription.end_date <= now,
            UserSubscription.is_active == True
        ).all()

        for subscription in expired_subscriptions:
            subscription.is_active = False
            logger.info(f"Отключена подписка ID {subscription.id} для пользователя ID {subscription.user_id}")

        db.commit()

        users_with_no_active_subs = db.query(User).filter(
            User.is_subscription == True
        ).all()

        for user in users_with_no_active_subs:
            active_sub = db.query(UserSubscription).filter(
                UserSubscription.user_id == user.id,
                UserSubscription.is_active == True,
                UserSubscription.end_date > datetime.utcnow()
            ).first()
            if not active_sub:
                user.is_subscription = False
                logger.info(f"Пользователю ID {user.id} установлено is_subscription = False")

        db.commit()

    logger.info("Проверка истекших подписок завершена")


def process_subscription_payment(user: User, subscription: UserSubscription, rebill_id: str):
    if IS_DEMO:
        logger.info("Recurring payment skipped in demo mode")
        return True, 0
    # Подготовка данных для запроса Charge
    amount = int(subscription.subscription.price * 100)  # сумма в копейках
    order_id = f"{subscription.id}-{int(datetime.utcnow().timestamp())}"
    payment_data = {
        "TerminalKey": TBANK_KASSA_TERMINAL,
        "Amount": amount,
        "RebillId": rebill_id,
        "OrderId": order_id,
        "Description": f"Автопродление подписки {subscription.subscription.name}",
        "CustomerKey": str(user.id),
    }

    # Отправка запроса Charge
    try:
        response = requests.post("https://securepay.tinkoff.ru/v2/Charge", json=payment_data)
        response.raise_for_status()
        result = response.json()
        if result.get("Success"):
            logger.info(f"Платеж на сумму {amount} для пользователя ID {user.id} прошел успешно")
            payment_id = result.get("PaymentId")
            return True, payment_id
        else:
            error_message = result.get('Message', 'Unknown error')
            logger.error(f"Ошибка при автоплатеже для пользователя ID {user.id}: {error_message}")
            return False, None
    except requests.RequestException as e:
        logger.exception(f"Сбой при обращении к платежному шлюзу для пользователя ID {user.id}: {e}")
        return False, None


def auto_renew_subscriptions():
    logger.info("Запуск автопродления подписок")
    utc_timezone = pytz.timezone('UTC')

    with SessionLocal() as db:
        now = utc_timezone.localize(datetime.utcnow())
        renewable_subscriptions = db.query(UserSubscription).filter(
            UserSubscription.renewable == True,
            UserSubscription.next_billing_date <= now,
            UserSubscription.is_active == True
        ).all()

        logger.info(f"Найдено подписок для автопродления: {len(renewable_subscriptions)}")

        for subscription in renewable_subscriptions:
            logger.info(f"Обработка подписки ID {subscription.id} для пользователя ID {subscription.user_id}")

            user = db.query(User).filter(User.id == subscription.user_id).first()
            if not user:
                logger.error(f"Пользователь с ID {subscription.user_id} не найден")
                continue

            # Получаем информацию о подписке
            sub_info = db.query(Subscription).filter(Subscription.id == subscription.subscription_id).first()
            if not sub_info:
                logger.error(f"Информация о подписке с ID {subscription.subscription_id} не найдена")
                continue

            # Устанавливаем цену из информации о подписке
            subscription.subscription = sub_info

            # Ищем последнюю успешную транзакцию с rebill_id
            last_transaction = db.query(Transaction).filter(
                Transaction.user_id == user.id,
                Transaction.subscription_id == subscription.subscription_id,
                Transaction.status == 'CONFIRMED',
                Transaction.rebill_id != None
            ).order_by(Transaction.transaction_date.desc()).first()

            if not last_transaction or not last_transaction.rebill_id:
                logger.warning(f"У пользователя ID {user.id} нет доступного RebillId для автоплатежа")
                continue

            rebill_id = last_transaction.rebill_id
            logger.info(f"Используем RebillId {rebill_id} для автоплатежа")

            payment_success, payment_id = process_subscription_payment(user, subscription, rebill_id)

            if payment_success:
                # Обновляем даты подписки
                subscription.start_date = datetime.utcnow()
                subscription.end_date = datetime.utcnow() + timedelta(days=sub_info.duration)
                subscription.next_billing_date = subscription.end_date
                logger.info(f"Продлена подписка ID {subscription.id} для пользователя ID {user.id} до {subscription.end_date}")

                # Создаем новую транзакцию для записи автоплатежа
                new_transaction = Transaction(
                    user_id=user.id,
                    subscription_id=subscription.subscription_id,
                    amount=sub_info.price,
                    transaction_date=datetime.utcnow(),
                    order_number=f"{subscription.subscription_id}-{int(datetime.utcnow().timestamp())}",
                    payment_id=payment_id or 0,
                    status='INITIATED',
                    rebill_id=rebill_id
                )
                db.add(new_transaction)

            else:
                subscription.is_active = False
                logger.warning(f"Не удалось продлить подписку ID {subscription.id} для пользователя ID {user.id}. Подписка деактивирована.")

            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.exception(f"Ошибка при автопродлении подписок: {e}")

    logger.info("Автопродление подписок завершено")


def start_scheduler():
    if IS_DEMO:
        logger.info("Payment scheduler disabled in demo mode")
        return None
    utc_timezone = pytz.timezone('UTC')
    scheduler = BackgroundScheduler(timezone=utc_timezone)
    scheduler.add_job(deactivate_expired_subscriptions, 'interval', hours=24, next_run_time=utc_timezone.localize(datetime.utcnow()))
    scheduler.add_job(auto_renew_subscriptions, 'interval', hours=1, next_run_time=utc_timezone.localize(datetime.utcnow()))
    scheduler.start()
    logger.info("Фоновый процесс APScheduler запущен")

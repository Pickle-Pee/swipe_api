from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from common.models import User, UserSubscription
from config import IS_DEMO, SessionLocal, logger


class RecurrentBillingDisabledError(RuntimeError):
    """Raised when the removed legacy recurrent billing path is invoked."""


def deactivate_expired_subscriptions(now: datetime | None = None) -> int:
    """Deactivate expired entitlements without contacting a payment provider.

    The operation is idempotent. Expired subscriptions cannot remain renewable:
    a future billing implementation must create and manage a separate mandate.
    """

    checked_at = now or datetime.utcnow()
    deactivated = 0
    with SessionLocal() as db:
        expired = (
            db.query(UserSubscription)
            .filter(
                UserSubscription.end_date <= checked_at,
                UserSubscription.is_active.is_(True),
            )
            .all()
        )
        affected_user_ids = {subscription.user_id for subscription in expired}
        for subscription in expired:
            subscription.is_active = False
            subscription.renewable = False
            subscription.next_billing_date = None
            deactivated += 1

        if affected_user_ids:
            users = db.query(User).filter(User.id.in_(affected_user_ids)).all()
            for user in users:
                has_active_subscription = (
                    db.query(UserSubscription)
                    .filter(
                        UserSubscription.user_id == user.id,
                        UserSubscription.is_active.is_(True),
                        UserSubscription.end_date > checked_at,
                    )
                    .first()
                    is not None
                )
                if not has_active_subscription:
                    user.is_subscription = False
        db.commit()

    logger.info("Expired subscription maintenance completed: count=%s", deactivated)
    return deactivated


def auto_renew_subscriptions() -> None:
    """Compatibility guard for the removed legacy billing entry point."""

    logger.warning("Recurrent billing is disabled; no renewal was attempted")
    raise RecurrentBillingDisabledError(
        "Recurrent billing is disabled and requires a separate implementation"
    )


def start_scheduler() -> BackgroundScheduler | None:
    """Start internal entitlement maintenance; never register a billing job."""

    if IS_DEMO:
        logger.info("Subscription maintenance scheduler disabled in demo mode")
        return None

    utc_timezone = pytz.timezone("UTC")
    scheduler = BackgroundScheduler(timezone=utc_timezone)
    scheduler.add_job(
        deactivate_expired_subscriptions,
        "interval",
        hours=24,
        id="deactivate_expired_subscriptions",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Subscription maintenance scheduler started")
    return scheduler

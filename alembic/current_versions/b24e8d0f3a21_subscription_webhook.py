"""add idempotent subscription webhook state

Revision ID: b24e8d0f3a21
Revises: a13f7c9d2e10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b24e8d0f3a21"
down_revision: Union[str, None] = "a13f7c9d2e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("subscription_activated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("bank_status", sa.String(), nullable=False),
        sa.Column("event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_fingerprint", name="uq_payment_webhook_event_fingerprint"
        ),
    )
    op.create_index(
        op.f("ix_payment_webhook_events_id"),
        "payment_webhook_events",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_webhook_events_payment_id"),
        "payment_webhook_events",
        ["payment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_webhook_events_payment_id"),
        table_name="payment_webhook_events",
    )
    op.drop_index(
        op.f("ix_payment_webhook_events_id"), table_name="payment_webhook_events"
    )
    op.drop_table("payment_webhook_events")
    op.drop_column("transactions", "subscription_activated_at")

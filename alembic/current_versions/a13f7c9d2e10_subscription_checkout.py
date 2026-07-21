"""add subscription checkout fields

Revision ID: a13f7c9d2e10
Revises: 5c0b937bc038
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a13f7c9d2e10"
down_revision: Union[str, None] = "5c0b937bc038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions", sa.Column("price_minor", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "currency", sa.String(length=3), server_default="RUB", nullable=False
        ),
    )
    op.add_column(
        "subscriptions", sa.Column("duration_days", sa.Integer(), nullable=True)
    )
    op.add_column("subscriptions", sa.Column("description", sa.Text(), nullable=True))
    op.execute(
        "UPDATE subscriptions SET price_minor = ROUND(price * 100), duration_days = duration, description = features"
    )

    op.alter_column("transactions", "order_number", new_column_name="order_id")
    op.alter_column(
        "transactions",
        "payment_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(),
        existing_nullable=False,
        nullable=True,
        postgresql_using="payment_id::text",
    )
    op.add_column(
        "transactions", sa.Column("amount_minor", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "transactions",
        sa.Column(
            "currency", sa.String(length=3), server_default="RUB", nullable=False
        ),
    )
    op.add_column("transactions", sa.Column("bank_status", sa.String(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "transactions", sa.Column("confirmed_at", sa.DateTime(), nullable=True)
    )
    op.add_column("transactions", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "transactions", sa.Column("error_code", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("error_message", sa.String(length=255), nullable=True)
    )
    op.execute(
        "UPDATE transactions SET amount_minor = ROUND(amount * 100), status = CASE WHEN status = 'INITIATED' THEN 'pending' ELSE LOWER(status) END"
    )
    op.create_unique_constraint(
        "uq_transactions_user_idempotency_key",
        "transactions",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_transactions_user_idempotency_key", "transactions", type_="unique"
    )
    for column in (
        "error_message",
        "error_code",
        "expires_at",
        "confirmed_at",
        "updated_at",
        "request_fingerprint",
        "idempotency_key",
        "bank_status",
        "currency",
        "amount_minor",
    ):
        op.drop_column("transactions", column)
    op.alter_column(
        "transactions",
        "payment_id",
        existing_type=sa.String(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        nullable=False,
        postgresql_using="payment_id::bigint",
    )
    op.alter_column("transactions", "order_id", new_column_name="order_number")
    for column in ("description", "duration_days", "currency", "price_minor"):
        op.drop_column("subscriptions", column)

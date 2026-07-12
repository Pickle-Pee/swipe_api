"""change children_pref type

Revision ID: 081a1f71838f
Revises: d14a0f02ae61
Create Date: 2024-11-12 22:59:44.694387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '081a1f71838f'
down_revision: Union[str, None] = 'd14a0f02ae61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создание ENUM типа 'childrenenum' если он ещё не существует
    children_enum = postgresql.ENUM(
        'PLANNING_CHILDREN',
        'HAVE_CHILDREN',
        'CHILDREN_OUTGROWN',
        'OPEN_TO_PARTNER_CHILDREN',
        'NO_CHILDREN',
        name='childrenenum'
    )
    children_enum.create(op.get_bind(), checkfirst=True)

    # Изменение типа столбца 'children_preference' на 'childrenenum' с использованием выражения CASE
    op.execute("""
        ALTER TABLE user_attributes
        ALTER COLUMN children_preference TYPE childrenenum
        USING CASE
            WHEN children_preference IS TRUE THEN 'HAVE_CHILDREN'
            WHEN children_preference IS FALSE THEN 'NO_CHILDREN'
            ELSE 'NO_CHILDREN' -- или другое значение по умолчанию
        END::childrenenum
    """)


def downgrade() -> None:
    # Изменение типа столбца 'children_preference' обратно на BOOLEAN с использованием выражения CASE
    op.execute("""
        ALTER TABLE user_attributes
        ALTER COLUMN children_preference TYPE BOOLEAN
        USING CASE
            WHEN children_preference = 'HAVE_CHILDREN' THEN TRUE
            WHEN children_preference = 'NO_CHILDREN' THEN FALSE
            ELSE FALSE
        END
    """)

    # Удаление ENUM типа 'childrenenum'
    children_enum = postgresql.ENUM(
        'PLANNING_CHILDREN',
        'HAVE_CHILDREN',
        'CHILDREN_OUTGROWN',
        'OPEN_TO_PARTNER_CHILDREN',
        'NO_CHILDREN',
        name='childrenenum'
    )
    children_enum.drop(op.get_bind(), checkfirst=True)

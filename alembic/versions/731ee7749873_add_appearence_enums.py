# alembic/versions/731ee7749873_add_appearance_enum.py
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '731ee7749873'
down_revision: Union[str, None] = 'b72e72841a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Создание Enum типа 'appearanceenum'
    appearanceenum = postgresql.ENUM(
        'ACTIVE_LIFESTYLE',
        'FASHION_FORWARD',
        'NATURAL_SIMPLE',
        'REFINED_STYLE',
        'TATTOO_PIERCING',
        'TIMELY_CLASSIC',
        'EXPERIMENTAL_STYLE',
        'SOFT_KIND_APPEARANCE',
        name='appearanceenum'
    )
    appearanceenum.create(op.get_bind())

    # 2. Изменение типа столбца 'appearance' на 'appearanceenum' с явным преобразованием
    op.execute("""
        ALTER TABLE user_attributes
        ALTER COLUMN appearance TYPE appearanceenum
        USING (
            CASE
                WHEN appearance = 'Активный образ жизни и забота о теле.' THEN 'ACTIVE_LIFESTYLE'::appearanceenum
                WHEN appearance = 'Люблю моду и следую последним трендам.' THEN 'FASHION_FORWARD'::appearanceenum
                WHEN appearance = 'Предпочитаю натуральный и простой вид.' THEN 'NATURAL_SIMPLE'::appearanceenum
                WHEN appearance = 'Обожаю изысканный и утончённый стиль.' THEN 'REFINED_STYLE'::appearanceenum
                WHEN appearance = 'Носитель татуировок и пирсинга.' THEN 'TATTOO_PIERCING'::appearanceenum
                WHEN appearance = 'Предпочитаю вечную классику в одежде и внешности.' THEN 'TIMELY_CLASSIC'::appearanceenum
                WHEN appearance = 'Люблю выделяться и экспериментировать со стилем.' THEN 'EXPERIMENTAL_STYLE'::appearanceenum
                WHEN appearance = 'Внешность отражает мягкость и доброту.' THEN 'SOFT_KIND_APPEARANCE'::appearanceenum
                ELSE NULL
            END
        )
    """)

def downgrade() -> None:
    # 1. Изменение типа столбца 'appearance' обратно на VARCHAR с явным преобразованием
    op.execute("""
        ALTER TABLE user_attributes
        ALTER COLUMN appearance TYPE VARCHAR
        USING (
            CASE
                WHEN appearance = 'ACTIVE_LIFESTYLE' THEN 'Активный образ жизни и забота о теле.'
                WHEN appearance = 'FASHION_FORWARD' THEN 'Люблю моду и следую последним трендам.'
                WHEN appearance = 'NATURAL_SIMPLE' THEN 'Предпочитаю натуральный и простой вид.'
                WHEN appearance = 'REFINED_STYLE' THEN 'Обожаю изысканный и утончённый стиль.'
                WHEN appearance = 'TATTOO_PIERCING' THEN 'Носитель татуировок и пирсинга.'
                WHEN appearance = 'TIMELY_CLASSIC' THEN 'Предпочитаю вечную классику в одежде и внешности.'
                WHEN appearance = 'EXPERIMENTAL_STYLE' THEN 'Люблю выделяться и экспериментировать со стилем.'
                WHEN appearance = 'SOFT_KIND_APPEARANCE' THEN 'Внешность отражает мягкость и доброту.'
                ELSE NULL
            END
        )
    """)

    # 2. Удаление Enum типа 'appearanceenum'
    appearanceenum = postgresql.ENUM(
        'ACTIVE_LIFESTYLE',
        'FASHION_FORWARD',
        'NATURAL_SIMPLE',
        'REFINED_STYLE',
        'TATTOO_PIERCING',
        'TIMELY_CLASSIC',
        'EXPERIMENTAL_STYLE',
        'SOFT_KIND_APPEARANCE',
        name='appearanceenum'
    )
    appearanceenum.drop(op.get_bind())

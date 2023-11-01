from config import SessionLocal
from sqlalchemy import text


def execute_sql(query: str, params: dict) -> list:
    """
    Выполняет SQL-запрос и возвращает результаты в виде списка словарей.
    """
    with SessionLocal() as db:
        result = db.execute(text(query), params)
        # Преобразование результатов в список словарей
        keys = result.keys()
        return [dict(zip(keys, row)) for row in result.fetchall()]

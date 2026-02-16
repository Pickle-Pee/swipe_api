from fastapi import HTTPException
from config import SessionLocal
from sqlalchemy import text
import openai

# proxies = {
#     "http": "http://94.241.173.216:3128",  # порт Squid по умолчанию
#     "https": "http://94.241.173.216:3128",
# }


def execute_sql(query: str, params: dict) -> list:
    """
    Выполняет SQL-запрос и возвращает результаты в виде списка словарей.
    """
    with SessionLocal() as db:
        result = db.execute(text(query), params)
        # Преобразование результатов в список словарей
        keys = result.keys()
        return [dict(zip(keys, row)) for row in result.fetchall()]


# def analyze_compatibility(profile_1: dict, profile_2: dict) -> float:
#     try:
#         prompt = f"""
#         User 1 Profile: {profile_1}
#         User 2 Profile: {profile_2}
#         Evaluate the compatibility of these two profiles on a scale from 0 to 100 and provide a brief explanation.
#         """
#         response = openai.Completion.create(
#             engine="davinci-codex",
#             prompt=prompt,
#             max_tokens=150,
#             request_kwargs={"proxies": proxies}
#         )
#         result = response.choices[0].text.strip()
#         try:
#             score = float(result.split()[0])
#         except ValueError:
#             score = 0.0
#         return score
#     except openai.error.PermissionError as e:
#         raise HTTPException(status_code=403, detail="OpenAI API is not supported in your country, region, or territory.")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail="An error occurred while analyzing compatibility.")
#

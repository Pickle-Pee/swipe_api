from random import shuffle, choice

from fastapi import HTTPException, APIRouter, Depends
from typing import List

from sqlalchemy import text

from common.models.cities_models import City
from common.schemas.match_schemas import MatchResponse
from common.models.user_models import User
from common.models.interests_models import Interest
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, SECRET_KEY


router = APIRouter(prefix="/match", tags=["Matches Controller"])


from datetime import datetime, timedelta


@router.get("/find_matches", response_model=List[MatchResponse])
def find_matches(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Получение списка интересов и городов
        interests_list = [i.interest_text for i in db.query(Interest).all()]
        cities_list = [c.city_name for c in db.query(City).all()]

        interests_str = ', '.join(["'%s'" % i for i in interests_list])
        cities_str = ', '.join(["'%s'" % c for c in cities_list])

        # Время, после которого лайкнутые пользователи снова появляются в поиске
        time_threshold = datetime.now() - timedelta(seconds=30)

        # SQL-запрос для поиска совпадений
        sql_query = text(f"""
        SELECT 
            users.id,
            users.first_name,
            users.last_name,
            users.date_of_birth,
            users.gender,
            users.city_id,
            users.verify,
            users.avatar_url,
            users.status,
            cities.city_name,
            COALESCE(SUM(
                CASE 
                    WHEN interests.interest_text IN ({interests_str}) THEN 3
                    ELSE 0
                END +
                CASE 
                    WHEN cities.city_name IN ({cities_str}) THEN 1
                    ELSE 0
                END
            ), 0) AS score
        FROM 
            users
        LEFT JOIN 
            user_interests ON users.id = user_interests.user_id
        LEFT JOIN 
            interests ON user_interests.interest_id = interests.id
        LEFT JOIN 
            cities ON users.city_id = cities.id
        WHERE 
            users.id != :user_id AND
            NOT EXISTS (
                SELECT 1 FROM likes 
                WHERE likes.liked_user_id = users.id AND likes.user_id = :user_id AND likes.timestamp > :time_threshold
            )
        GROUP BY 
            users.id, users.first_name, users.last_name, cities.city_name
        ORDER BY 
            score DESC, RANDOM()
        LIMIT 10;
        """)

        result = db.execute(sql_query, {'user_id': user_id, 'time_threshold': time_threshold}).fetchall()

        matches = [
            MatchResponse(
                user_id=row.id,
                first_name=row.first_name,
                date_of_birth=row.date_of_birth,
                gender=row.gender if row.gender is not None else "Unknown",
                status=row.status,
                city_name=row.city_name,
                avatar_url=row.avatar_url
            )
            for row in result
        ]

        return matches

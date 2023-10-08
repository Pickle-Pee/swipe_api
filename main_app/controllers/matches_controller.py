from fastapi import HTTPException, APIRouter, Depends
from typing import List
from sqlalchemy import text
from common.models.cities_models import City
from common.schemas.match_schemas import MatchResponse
from common.models.user_models import User
from common.models.interests_models import Interest
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, logger
from datetime import datetime, timedelta


router = APIRouter(prefix="/match", tags=["Matches Controller"])


@router.get("/find_matches", response_model=List[MatchResponse])
def find_matches(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.city_id or not user.gender:
            raise HTTPException(status_code=404, detail="User not found or profile incomplete")

        current_date = datetime.now()
        user_age = current_date.year - user.date_of_birth.year - (
                    (current_date.month, current_date.day) < (user.date_of_birth.month, user.date_of_birth.day))

        age_difference = 5
        min_age = current_date - timedelta(days=(user_age + age_difference) * 365.25)
        max_age = current_date - timedelta(days=(user_age - age_difference) * 365.25)

        sql_query = text(
            f"""
            SELECT 
                users.id,
                users.first_name,
                users.date_of_birth,
                users.gender,
                users.status,
                users.verify,
                cities.city_name,
                user_photos.photo_url as avatar_url,
                COUNT(interests.id) AS common_interests_count
            FROM 
                users
            JOIN 
                cities ON users.city_id = cities.id
            LEFT JOIN 
                user_interests ON users.id = user_interests.user_id
            LEFT JOIN 
                interests ON user_interests.interest_id = interests.id
            LEFT JOIN 
                user_photos ON users.id = user_photos.user_id AND user_photos.is_avatar = TRUE
            WHERE 
                users.id != :user_id AND
                users.city_id = :city_id AND 
                users.gender != :gender AND
                users.verify = TRUE AND
                users.date_of_birth BETWEEN :min_age AND :max_age AND
                NOT EXISTS (
                    SELECT 1 FROM likes 
                    WHERE likes.liked_user_id = users.id AND likes.user_id = :user_id
                )
            GROUP BY 
                users.id, cities.city_name, user_photos.photo_url
            ORDER BY 
                common_interests_count DESC, RANDOM()
            LIMIT 10;
            """
        )

        params = {
            'user_id': user_id,
            'city_id': user.city_id,
            'gender': user.gender,
            'min_age': min_age,
            'max_age': max_age
        }

        result = db.execute(sql_query, params).fetchall()
        logger.debug("SQL query: %s", sql_query)
        logger.debug("Parameters: %s", params)

        matches = [
            MatchResponse(
                user_id=row.id,
                first_name=row.first_name,
                date_of_birth=row.date_of_birth,
                gender=row.gender if row.gender else "Unknown",
                status=row.status,
                city_name=row.city_name,
                avatar_url=row.avatar_url,
                verify=row.verify
            )
            for row in result
        ]

        return matches

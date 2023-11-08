from fastapi import HTTPException, APIRouter, Depends
from typing import List

from common.models import User, UserPhoto, City
from common.schemas import MatchResponse
from common.utils import execute_sql
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, MAX_DISTANCE

router = APIRouter(prefix="/match", tags=["Matches Controller"])

@router.get("/find_matches", response_model=List[MatchResponse])
def find_matches(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user or not current_user.city_id or not current_user.gender:
            raise HTTPException(status_code=404, detail="User not found or profile incomplete")

        # Извлечение потенциальных соответствий
        potential_matches = execute_sql(
            """
            WITH distances AS (
                SELECT
                    u2.id AS potential_match_id,
                    u2.first_name,
                    u2.date_of_birth,
                    u2.gender,
                    u2.city_id,
                    (6371 * acos(cos(radians(u1_geo.latitude)) * cos(radians(u2_geo.latitude)) * cos(radians(u2_geo.longitude) - radians(u1_geo.longitude)) + sin(radians(u1_geo.latitude)) * sin(radians(u2_geo.latitude)))) AS distance
                FROM users u1
                JOIN users u2 ON u1.id != u2.id AND u1.gender != u2.gender AND u2.deleted = false
                LEFT JOIN user_geolocation u1_geo ON u1.id = u1_geo.user_id
                LEFT JOIN user_geolocation u2_geo ON u2.id = u2_geo.user_id
                WHERE u1.id = :current_user_id
            )
            
            SELECT
                d.potential_match_id,
                d.first_name,
                d.date_of_birth,
                d.gender,
                d.city_id,
                d.distance,
                COUNT(ui2.interest_id) AS common_interests_count -- Исправлено здесь
            FROM distances d
            LEFT JOIN user_interests ui1 ON ui1.user_id = :current_user_id
            LEFT JOIN user_interests ui2 ON ui2.user_id = d.potential_match_id AND ui1.interest_id = ui2.interest_id
            WHERE d.potential_match_id NOT IN (SELECT liked_user_id FROM likes WHERE user_id = :current_user_id)
            AND d.potential_match_id NOT IN (SELECT disliked_user_id FROM dislikes WHERE user_id = :current_user_id)
            GROUP BY d.potential_match_id, d.first_name, d.date_of_birth, d.gender, d.city_id, d.distance
            """, params={"current_user_id": user_id}
            )

        # Формирование ответа
        response = []
        for match in potential_matches:
            avatar_query = db.query(UserPhoto.photo_url).filter(
                UserPhoto.user_id == match["potential_match_id"], UserPhoto.is_avatar == True
                ).first()
            avatar_url = avatar_query[0] if avatar_query else None

            interests_percentage = (match["common_interests_count"] / len(
                current_user.interests
                )) * 100 if current_user.interests else 0
            distance_percentage = 100 if match["distance"] and match["distance"] <= MAX_DISTANCE else 0
            match_percentage = (interests_percentage + distance_percentage) / 2

            response.append(
                MatchResponse(
                    user_id=match["potential_match_id"],
                    first_name=match["first_name"],
                    date_of_birth=match["date_of_birth"],
                    gender=match["gender"],
                    city_name=db.query(City.city_name).filter(City.id == match["city_id"]).first()[0] if match[
                        "city_id"] else None,
                    interests=[interest.interest.interest_text for interest in
                               db.query(User).filter(User.id == match["potential_match_id"]).first().interests],
                    avatar_url=avatar_url,
                    match_percentage=match_percentage
                )
            )

            response = sorted(response, key=lambda x: x.match_percentage, reverse=True)

    return response




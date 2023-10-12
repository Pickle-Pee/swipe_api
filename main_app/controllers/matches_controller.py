import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException, APIRouter, Depends
from typing import List
from sqlalchemy import text
from common.models.cities_models import City
from common.schemas.match_schemas import MatchResponse
from common.models.user_models import User
from common.models.interests_models import Interest, UserInterest
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, logger
from datetime import datetime, timedelta

model = joblib.load('/app/common/utils/best_model.pkl')
router = APIRouter(prefix="/match", tags=["Matches Controller"])


# @router.get("/find_matches", response_model=List[MatchResponse])
# def find_matches(access_token: str = Depends(get_token)):
#     with SessionLocal() as db:
#         user_id = get_user_id_from_token(access_token)
#         user = db.query(User).filter(User.id == user_id).first()
#         if not user or not user.city_id or not user.gender:
#             raise HTTPException(status_code=404, detail="User not found or profile incomplete")
#
#         current_date = datetime.now()
#         user_age = current_date.year - user.date_of_birth.year - (
#                     (current_date.month, current_date.day) < (user.date_of_birth.month, user.date_of_birth.day))
#
#         age_difference = 5
#         min_age = current_date - timedelta(days=(user_age + age_difference) * 365.25)
#         max_age = current_date - timedelta(days=(user_age - age_difference) * 365.25)
#
#         sql_query = text(
#             f"""
#             SELECT
#                 users.id,
#                 users.first_name,
#                 users.date_of_birth,
#                 users.gender,
#                 users.status,
#                 users.verify,
#                 cities.city_name,
#                 user_photos.photo_url as avatar_url,
#                 COUNT(interests.id) AS common_interests_count
#             FROM
#                 users
#             JOIN
#                 cities ON users.city_id = cities.id
#             LEFT JOIN
#                 user_interests ON users.id = user_interests.user_id
#             LEFT JOIN
#                 interests ON user_interests.interest_id = interests.id
#             LEFT JOIN
#                 user_photos ON users.id = user_photos.user_id AND user_photos.is_avatar = TRUE
#             WHERE
#                 users.id != :user_id AND
#                 users.city_id = :city_id AND
#                 users.gender != :gender AND
#                 users.verify = TRUE AND
#                 users.date_of_birth BETWEEN :min_age AND :max_age AND
#                 NOT EXISTS (
#                     SELECT 1 FROM likes
#                     WHERE likes.liked_user_id = users.id AND likes.user_id = :user_id
#                 )
#             GROUP BY
#                 users.id, cities.city_name, user_photos.photo_url
#             ORDER BY
#                 common_interests_count DESC, RANDOM()
#             LIMIT 10;
#             """
#         )
#
#         params = {
#             'user_id': user_id,
#             'city_id': user.city_id,
#             'gender': user.gender,
#             'min_age': min_age,
#             'max_age': max_age
#         }
#
#         result = db.execute(sql_query, params).fetchall()
#         logger.debug("SQL query: %s", sql_query)
#         logger.debug("Parameters: %s", params)
#
#         matches = [
#             MatchResponse(
#                 user_id=row.id,
#                 first_name=row.first_name,
#                 date_of_birth=row.date_of_birth,
#                 gender=row.gender if row.gender else "Unknown",
#                 status=row.status,
#                 city_name=row.city_name,
#                 avatar_url=row.avatar_url,
#                 verify=row.verify
#             )
#             for row in result
#         ]
#
#         return matches

@router.get("/find_matches", response_model=List[MatchResponse])
def find_matches(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.city_id or not user.gender:
            raise HTTPException(status_code=404, detail="User not found or profile incomplete")
        users = db.query(User).all()

        if not users:
            raise HTTPException(status_code=404, detail="No users found")

        user_interests = db.query(Interest.interest_text).join(UserInterest).filter(UserInterest.user_id == user_id).all()
        user_interests = [interest[0] for interest in user_interests]


        data = pd.DataFrame([{
            'first_name': user.first_name,
            'age': (datetime.now().date() - user.date_of_birth).days // 365,
            'interests': ','.join(user_interests),
            'city': db.query(City.city_name).filter(City.id == user.city_id).first()[0] if user.city_id else None,
            'latitude': user.user_geolocation.latitude if user.user_geolocation else None,
            'longitude': user.user_geolocation.longitude if user.user_geolocation else None,
            'gender': user.gender
        } for user in users])

        numerical_data = data.select_dtypes(include=[np.number])
        numerical_data.fillna(numerical_data.mean(), inplace=True)

        non_numerical_data = data.select_dtypes(exclude=[np.number])
        non_numerical_data.fillna('missing', inplace=True)

        data = pd.concat([numerical_data, non_numerical_data], axis=1)

        predictions = model.predict(data)
        matched_users = [users[i] for i in range(len(users)) if predictions[i] == 1]
        response = [
            MatchResponse(
                user_id=user.id,
                first_name=user.first_name,
                date_of_birth=user.date_of_birth,
                gender=user.gender,
                city_name=user.city.city_name,
                interests=[interest.interest.interest_text for interest in user.interests]
            ) for user in matched_users
        ]

    return response

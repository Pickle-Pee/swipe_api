import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException, APIRouter, Depends
from typing import List
from datetime import datetime
from common.models import City, Interest, UserInterest, User, UserPhoto
from common.schemas import MatchResponse
from common.utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal


model = joblib.load('/app/common/utils/best_model.pkl')
router = APIRouter(prefix="/match", tags=["Matches Controller"])

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

        response = []
        for user in matched_users:
            avatar_query = db.query(UserPhoto.photo_url).filter(UserPhoto.user_id == user.id, UserPhoto.is_avatar == True).first()
            avatar_url = avatar_query[0] if avatar_query else None
            response.append(
                MatchResponse(
                    user_id=user.id,
                    first_name=user.first_name,
                    date_of_birth=user.date_of_birth,
                    gender=user.gender,
                    city_name=user.city.city_name if user.city else None,
                    interests=[interest.interest.interest_text for interest in user.interests],
                    avatar_url=avatar_url
                )
            )

    return response


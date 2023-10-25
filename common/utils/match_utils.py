import re
import warnings
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import DataConversionWarning
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

from common.models import City, Interest, UserInterest, Favorite
from config import SessionLocal

model = joblib.load('/app/common/utils/best_model.pkl')

def parse_interests(interests_str):
    return re.findall(r'\w+', interests_str)


def check_if_favorite(user_id: int, other_user_id: int) -> bool:
    with SessionLocal() as db:
        favorite_entry = db.query(Favorite).filter(
            Favorite.user_id == user_id,
            Favorite.favorite_user_id == other_user_id
        ).first()

        return bool(favorite_entry)


def get_neural_network_match_percentage(user1, user2):
    with SessionLocal() as db:
        users = [user1, user2]

        user_interests1 = db.query(Interest.interest_text).join(UserInterest).filter(UserInterest.user_id == user1.id).all()
        user_interests1 = [interest[0] for interest in user_interests1]

        user_interests2 = db.query(Interest.interest_text).join(UserInterest).filter(UserInterest.user_id == user2.id).all()
        user_interests2 = [interest[0] for interest in user_interests2]

        data = pd.DataFrame([{
            'first_name': user.first_name,
            'age': (datetime.now().date() - user.date_of_birth).days // 365,
            'interests': ','.join(user_interests1 if user.id == user1.id else user_interests2) if user_interests1 or user_interests2 else None,
            'city': db.query(City.city_name).filter(City.id == user.city_id).first()[0] if user.city_id else None,
            'latitude': user.user_geolocation.latitude if user.user_geolocation else None,
            'longitude': user.user_geolocation.longitude if user.user_geolocation else None,
            'gender': user.gender if user.gender else None
        } for user in users])

        numerical_data = data.select_dtypes(include=[np.number])

        if 'latitude' in numerical_data.columns:
            numerical_data['latitude'].fillna(numerical_data['latitude'].mean(), inplace=True)
        if 'longitude' in numerical_data.columns:
            numerical_data['longitude'].fillna(numerical_data['longitude'].mean(), inplace=True)

        non_numerical_data = data.select_dtypes(exclude=[np.number])

        for column in ['gender', 'city', 'interests']:
            if column in non_numerical_data.columns:
                non_numerical_data[column].fillna('missing', inplace=True)

        non_numerical_data = pd.get_dummies(non_numerical_data, dummy_na=True, drop_first=True)

        data = pd.concat([numerical_data, non_numerical_data], axis=1)

        # Normalize the data to have values between 0 and 1
        scaler = MinMaxScaler()
        normalized_data = scaler.fit_transform(data)

        # Compute cosine similarity
        similarity = cosine_similarity([normalized_data[0]], [normalized_data[1]])

        # Convert cosine similarity to a percentage
        match_percentage = max(similarity[0][0], 0) * 100

        return match_percentage

warnings.filterwarnings(action='ignore', category=DataConversionWarning)
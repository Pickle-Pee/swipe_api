from fastapi import HTTPException, APIRouter, Depends
from typing import List, Optional

from sqlalchemy import text

from common.models.cities_models import City
from common.models.interests_models import Interest, UserInterest
from config import SessionLocal, SECRET_KEY, logger
from common.models.user_models import User, PushTokens
from common.schemas.user_schemas import UserDataResponse, AddTokenRequest
from common.utils.auth_utils import get_token, get_user_id_from_token
import traceback
import requests
import random

router = APIRouter(prefix="/user", tags=["User Controller"])


@router.get("/me", response_model=UserDataResponse, summary="Получение информации о текущем пользователе")
def get_current_user(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()
            city = db.query(City).filter(City.id == user.city_id).first()
            city_name = city.city_name if city else None
            user_interests = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
            interests = [db.query(Interest).filter(Interest.id == ui.interest_id).first().interest_text for ui in
                         user_interests]
            if user:
                return {
                    "id": user.id,
                    "first_name": user.first_name if user.first_name else None,
                    "last_name": user.last_name if user.last_name else None,
                    "date_of_birth": user.date_of_birth if user.date_of_birth else None,
                    "gender": user.gender if user.gender else None,
                    "verify": user.verify,
                    "is_subscription": user.is_subscription,
                    "city_name": city_name,
                    "interests": interests,
                    "about_me": user.about_me
                }
            else:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
        except Exception as e:
            traceback.print_exc()
            print("Error retrieving user:", e)
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{user_id}", response_model=UserDataResponse, summary="Получение информации о пользователе")
def get_user(user_id: Optional[int] = None, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            if user_id is None:
                user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                interests_list = [i.interest_text for i in db.query(Interest).all()]
                cities_list = [c.city_name for c in db.query(City).all()]

                interests_str = ', '.join(["'%s'" % i for i in interests_list])
                cities_str = ', '.join(["'%s'" % c for c in cities_list])

                sql_query = text(f"""
                    SELECT 
                        users.id,
                        users.first_name,
                        users.last_name,
                        users.date_of_birth,
                        users.gender,
                        users.city_id,
                        users.verify,
                        cities.city_name,
                        ROUND(
                            (SUM(
                                CASE 
                                    WHEN interests.interest_text IN ({interests_str}) THEN 3
                                    ELSE 0
                                END +
                                CASE 
                                    WHEN cities.city_name IN ({cities_str}) THEN 1
                                    ELSE 0
                                END
                            ) / 49.0) * 100
                        ) AS match_percentage
                    FROM 
                        users
                    LEFT JOIN 
                        user_interests ON users.id = user_interests.user_id
                    LEFT JOIN 
                        interests ON user_interests.interest_id = interests.id
                    LEFT JOIN 
                        cities ON users.city_id = cities.id
                    WHERE 
                        users.id = :user_id
                    GROUP BY 
                        users.id, users.first_name, users.last_name, cities.city_name;
                                """)

                result = db.execute(sql_query, {'user_id': user_id}).fetchone()
                match_percentage = int(result.match_percentage) if result else 0

                user_interests = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
                interests = [db.query(Interest).filter(Interest.id == ui.interest_id).first().interest_text for ui in
                             user_interests]

                return {
                    "id": user.id,
                    "first_name": user.first_name if user.first_name else None,
                    "last_name": user.last_name if user.last_name else None,
                    "date_of_birth": user.date_of_birth if user.date_of_birth else None,
                    "gender": user.gender if user.gender else None,
                    "verify": user.verify,
                    "is_subscription": user.is_subscription,
                    "about_me": user.about_me,
                    "status": user.status,
                    "city_name": result.city_name if result else None,
                    "interests": interests,
                    "match_percentage": match_percentage

                }
            else:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
        except Exception as e:
            traceback.print_exc()
            print("Error retrieving user:", e)
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/all_users", response_model=List[UserDataResponse], summary="Получение списка всех пользователей")
def get_all_users():
    with SessionLocal() as db:
        try:
            users = db.query(User).all()
            user_data_list = [
                {
                    "id": user.id,
                    "phone_number": user.phone_number,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "date_of_birth": user.date_of_birth,
                    "gender": user.gender,
                    "verify": user.verify,
                    "is_subscription": user.is_subscription
                }
                for user in users
            ]
            return user_data_list
        except Exception as e:
            print("Error retrieving users:", e)
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add_random_photos")
def add_random_avatars_to_users():
    with SessionLocal() as db:
        response = requests.get("https://64ff6fe5f8b9eeca9e2a2278.mockapi.io/avatars/avatars")
        avatars = response.json()

        # Извлечение URL-ов фото
        avatar_urls = [avatar['avatar'] for avatar in avatars]

        # Добавление рандомных URL-ов в базу данных
        users = db.query(User).all()
        for user in users:
            random_avatar_url = random.choice(avatar_urls)
            user.avatar_url = random_avatar_url
        db.commit()


@router.post("/add_token", summary="Добавление или обновление токена пользователя")
def add_token(request: AddTokenRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            existing_push_token = db.query(PushTokens).filter(PushTokens.userid == user_id).first()

            if existing_push_token:
                # Обновление существующего токена
                existing_push_token.token = request.token
                existing_push_token.active = True
                message = "Токен обновлен"
            else:
                # Добавление нового токена
                new_push_token = PushTokens(userid=user_id, token=request.token, active=True)
                db.add(new_push_token)
                message = "Токен добавлен"

            db.commit()
            return {"message": message}

        except Exception as e:
            print("Exception:", e)
            logger.error('Error: %s', e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


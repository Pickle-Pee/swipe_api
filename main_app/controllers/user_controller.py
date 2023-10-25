from datetime import datetime

from fastapi import HTTPException, APIRouter, Depends, status
from fastapi.responses import Response
from typing import List, Optional
from common.models import City, User, PushTokens, UserPhoto, UserGeolocation, Interest, UserInterest
from common.utils.crud import delete_user_and_related_data
from common.utils.match_utils import get_neural_network_match_percentage
from config import SessionLocal, logger
from common.schemas.user_schemas import UserDataResponse, AddTokenRequest, PersonalUserDataResponse, InterestResponse, \
    UpdateUserRequest, UserPhotosResponse, AddGeolocationRequest
from common.utils.auth_utils import get_token, get_user_id_from_token
import traceback
import requests
import random

router = APIRouter(prefix="/user", tags=["User Controller"])


@router.get("/me", response_model=PersonalUserDataResponse, summary="Получение информации о текущем пользователе")
async def get_current_user(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).one_or_none()

        if user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        city_name = db.query(City.city_name).filter(City.id == user.city_id).scalar()

        interests_data = db.query(Interest.id, Interest.interest_text).join(
            UserInterest, UserInterest.interest_id == Interest.id
        ).filter(UserInterest.user_id == user_id).all()

        interests = [InterestResponse(interest_id=id, interest_text=text) for id, text in interests_data]

        avatar = db.query(UserPhoto).filter(
            UserPhoto.user_id == user_id,
            UserPhoto.is_avatar.is_(True)
        ).first()

        avatar_url = avatar.photo_url if avatar else None

        return {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_of_birth": user.date_of_birth,
            "gender": user.gender,
            "is_subscription": user.is_subscription,
            "city_name": city_name,
            "interests": interests if interests else None,
            "about_me": user.about_me,
            "status": user.status,
            "avatar_url": avatar_url,
            "deleted": user.deleted
        }


@router.get("/{user_id}", response_model=UserDataResponse, summary="Получение информации о пользователе")
def get_user(user_id: Optional[int] = None, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            if user_id is None:
                user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                current_user_id = get_user_id_from_token(access_token)
                current_user = db.query(User).filter(User.id == current_user_id).first()

                match_percentage = get_neural_network_match_percentage(current_user, user)

                interests_data = db.query(Interest.id, Interest.interest_text).join(
                    UserInterest, UserInterest.interest_id == Interest.id
                ).filter(UserInterest.user_id == user_id).all()

                interests = [InterestResponse(interest_id=id, interest_text=text) for id, text in interests_data]

                return {
                    "id": user.id,
                    "first_name": user.first_name if user.first_name else None,
                    "last_name": user.last_name if user.last_name else None,
                    "date_of_birth": user.date_of_birth if user.date_of_birth else None,
                    "gender": user.gender if user.gender else None,
                    "is_subscription": user.is_subscription,
                    "about_me": user.about_me,
                    "status": user.status,
                    "city_name": db.query(City.city_name).filter(
                        City.id == user.city_id
                        ).scalar() if user.city_id else None,
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

            existing_push_token = db.query(PushTokens).filter(PushTokens.user_id == user_id).first()

            if existing_push_token:
                # Обновление существующего токена
                existing_push_token.token = request.token
                existing_push_token.active = True
                message = "Токен обновлен"
            else:
                # Добавление нового токена
                new_push_token = PushTokens(user_id=user_id, token=request.token, active=True)
                db.add(new_push_token)
                message = "Токен добавлен"

            db.commit()
            return {"message": message}

        except Exception as e:
            print("Exception:", e)
            logger.error('Error: %s', e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/delete_user", summary="Удаление профиля")
def delete_user(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        if not user_id:
            raise HTTPException(
                status_code=404,
                detail="Пользователь не найден"
            )

        success = delete_user_and_related_data(db, user_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Пользователь не найден или не может быть удален"
            )

        return {"status": "success", "message": "Профиль удален"}


@router.put("/update_user", status_code=201, summary="Обновление данных пользователя")
async def update_user(data: UpdateUserRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            if data.first_name:
                user.first_name = data.first_name

            if data.date_of_birth:
                user.date_of_birth = data.date_of_birth

            if data.gender:
                user.gender = data.gender

            if data.city_name:
                city = db.query(City).filter(City.city_name == data.city_name).first()
                if city:
                    user.city_id = city.id

            if data.about_me:
                user.about_me = data.about_me

            db.commit()

            return Response(status_code=201)

        except Exception as e:
            print("Exception:", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/set_avatar/{photo_id}")
async def set_avatar(photo_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            photo = db.query(UserPhoto).filter(UserPhoto.id == photo_id, UserPhoto.user_id == user_id).first()

            if not photo:
                raise HTTPException(status_code=200, detail="Фотография не найдена")

            photo.set_as_avatar(db)

        except Exception as e:
            print("Exception:", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    return {"detail": "Аватар успешно установлен"}


@router.get("/user/photos", response_model=UserPhotosResponse)
async def get_user_photos(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)

            photos = db.query(UserPhoto).filter(UserPhoto.user_id == user_id).all()

            if not photos:
                return {"photos": []}

        except Exception as e:
            print("Exception:", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    return {"photos": photos}


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(photo_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            photo = db.query(UserPhoto).filter(UserPhoto.id == photo_id, UserPhoto.user_id == user_id).first()

            if not photo:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Фото не найдено")

            db.delete(photo)
            db.commit()

        except Exception as e:
            print("Exception:", e)
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/add_geolocation", summary="Добавление или обновление геопозиции пользователя")
def add_geolocation(request: AddGeolocationRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            existing_geolocation = db.query(UserGeolocation).filter(UserGeolocation.user_id == user_id).first()

            if existing_geolocation:
                existing_geolocation.latitude = request.latitude
                existing_geolocation.longitude = request.longitude
                existing_geolocation.updated_at = datetime.now()
                message = "Геопозиция обновлена"
            else:
                new_geolocation = UserGeolocation(
                    user_id=user_id,
                    latitude=request.latitude,
                    longitude=request.longitude
                )
                db.add(new_geolocation)
                message = "Геопозиция добавлена"

            db.commit()
            return {"message": message}

        except Exception as e:
            print("Exception:", e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/verify/check_verify", summary="Получение информации о верификации")
async def get_current_user(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).one_or_none()

        if user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        return {
            "verify": user.verify
        }
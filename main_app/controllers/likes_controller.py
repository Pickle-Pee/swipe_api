from datetime import timedelta, datetime
from typing import List
from sqlalchemy.orm import joinedload
from fastapi import Depends, APIRouter, HTTPException
from config import SessionLocal
from common.models import Like, Dislike, Favorite, User, UserPhoto, City
from common.schemas import FavoriteCreate, UserLikesResponse
from common.utils import get_token, get_user_id_from_token

router = APIRouter(prefix="/likes", tags=["Likes Controller"])


@router.post("/like/{user_id}", summary="Лайкнуть пользователя")
def like_user(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        # Проверка на взаимный лайк
        with db.begin():
            mutual_like = db.query(Like).filter(Like.user_id == user_id, Like.liked_user_id == current_user_id).first()
            if mutual_like:
                mutual_like.mutual = True
                db.commit()
                return {"message": "It's a match!"}

            existing_like = db.query(Like).filter(Like.user_id == current_user_id, Like.liked_user_id == user_id).first()
            if existing_like:
                raise HTTPException(status_code=400, detail="Already liked")

            new_like = Like(user_id=current_user_id, liked_user_id=user_id)
            db.add(new_like)
            db.commit()

        return {"message": "Liked"}


@router.post("/dislike/{user_id}", summary="Дизлайкнуть пользователя")
def dislike_user(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        new_dislike = Dislike(
            user_id=current_user_id,
            disliked_user_id=user_id,
            timestamp=datetime.utcnow() + timedelta(days=2)
        )
        db.add(new_dislike)
        db.commit()
        return {"message": "Disliked"}


@router.post("/add_to_favorites/{user_id}", response_model=FavoriteCreate, summary="Добавить в избранное")
def add_to_favorites(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        # Проверка, чтобы пользователь не добавил сам себя в избранное
        if current_user_id == user_id:
            raise HTTPException(status_code=400, detail="You cannot add yourself to favorites")

        # Проверка на существование пользователя в базе данных
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Проверка, чтобы не добавить одного и того же пользователя в избранное несколько раз
        existing_favorite = db.query(Favorite).filter(
            Favorite.user_id == current_user_id, Favorite.favorite_user_id == user_id
        ).first()
        if existing_favorite:
            raise HTTPException(status_code=400, detail="Already added to favorites")

        # Добавление пользователя в избранное
        db_favorite = Favorite(user_id=current_user_id, favorite_user_id=user_id)
        db.add(db_favorite)
        db.commit()
        db.refresh(db_favorite)
        return db_favorite


@router.get("/favorites", response_model=List[UserLikesResponse], summary="Список избранных")
def get_favorites(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)
        favorites = db.query(User).options(joinedload(User.interests)).join(
            Favorite, User.id == Favorite.favorite_user_id
        ).filter(
            Favorite.user_id == current_user_id
        ).all()

        response = []
        for user in favorites:
            avatar_url = db.query(UserPhoto.photo_url).filter(
                UserPhoto.user_id == user.id, UserPhoto.is_avatar == True
            ).first()
            city_name = db.query(City.city_name).filter(City.id == user.city_id).first()
            response.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "avatar_url": avatar_url[0] if avatar_url else None,
                    "date_of_birth": user.date_of_birth,
                    "city_name": city_name[0] if city_name else None,
                    # "is_favorite": user.is_favorite,
                    "about_me": user.about_me,
                    "status": user.status
                }
            )
        return response


@router.get("/liked_me", response_model=List[UserLikesResponse], summary="Список пользователей, лайкнувших меня")
def get_liked_by(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)
        liked_by_users = db.query(User).join(Like, User.id == Like.user_id).filter(
            Like.liked_user_id == current_user_id).all()


        response = []
        for user in liked_by_users:
            avatar_url = db.query(UserPhoto.photo_url).filter(
                UserPhoto.user_id == user.id, UserPhoto.is_avatar == True).first()
            city_name = db.query(City.city_name).filter(City.id == user.city_id).first()
            response.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "avatar_url": avatar_url[0] if avatar_url else None,
                    "date_of_birth": user.date_of_birth,
                    "city_name": city_name,
                    # "is_favorite": user.is_favorite,
                    "about_me": user.about_me,
                    "status": user.status
                }
            )
        return response


@router.get("/liked_users", response_model=List[UserLikesResponse], summary="Список пользователей, которых лайкнул я")
def get_liked_users(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        # Запрос на получение пользователей, которых текущий пользователь лайкнул
        liked_users = db.query(User).join(Like, User.id == Like.liked_user_id).filter(
            Like.user_id == current_user_id
            ).all()

        response = []
        for user in liked_users:
            avatar_url = db.query(UserPhoto.photo_url).filter(
                UserPhoto.user_id == user.id, UserPhoto.is_avatar == True
                ).first()
            city_name = db.query(City.city_name).filter(City.id == user.city_id).first()
            response.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "avatar_url": avatar_url[0] if avatar_url else None,
                    "date_of_birth": user.date_of_birth,
                    "city_name": city_name[0] if city_name else None,
                    # "is_favorite": user.is_favorite,
                    "about_me": user.about_me,
                    "status": user.status
                }
            )
        return response


@router.delete("/remove_from_favorites/{user_id}", summary="Удалить из избранного")
def remove_from_favorites(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:  # Или ваш способ получения сессии
        current_user_id = get_user_id_from_token(access_token)

        # Находим запись в избранном для удаления
        favorite_to_remove = db.query(Favorite).filter(
            Favorite.user_id == current_user_id, Favorite.favorite_user_id == user_id
        ).first()

        if not favorite_to_remove:
            raise HTTPException(status_code=404, detail="User not found in favorites")

        # Удаляем пользователя из избранного
        db.delete(favorite_to_remove)
        db.commit()

        return {"message": "User removed from favorites"}
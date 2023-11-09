from datetime import timedelta, datetime
from typing import List
from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.orm import joinedload
from config import SessionLocal, MAX_DISTANCE
from common.models import Like, Dislike, Favorite, User, UserPhoto, City
from common.schemas import FavoriteCreate, UserLikesResponse
from common.utils import get_token, get_user_id_from_token, execute_sql

router = APIRouter(prefix="/likes", tags=["Likes Controller"])


@router.post("/like/{user_id}", summary="Лайкнуть пользователя")
def like_user(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)

        # Проверка на взаимный лайк
        with db.begin():
            # Проверяем, поставил ли пользователь с user_id лайк текущему пользователю
            mutual_like = db.query(Like).filter(Like.user_id == user_id, Like.liked_user_id == current_user_id).first()

            # Проверяем, поставил ли текущий пользователь лайк пользователю с user_id
            existing_like = db.query(Like).filter(
                Like.user_id == current_user_id, Like.liked_user_id == user_id
                ).first()

            # Если уже существует лайк от текущего пользователя, возвращаем ошибку
            if existing_like:
                raise HTTPException(status_code=200, detail="Already liked")

            # Если найден взаимный лайк, обновляем обе записи
            if mutual_like:
                mutual_like.mutual = True
                # Создаём новую запись лайка для текущего пользователя
                new_like = Like(user_id=current_user_id, liked_user_id=user_id, mutual=True)
                db.add(new_like)
                db.commit()
                return {"message": "It's a match!"}

            # Если взаимного лайка нет, создаём новую запись лайка
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
        current_user = db.query(User).options(joinedload(User.interests)).filter(User.id == current_user_id).first()

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
            """, params={"current_user_id": current_user_id}
        )

        match_info = {match["potential_match_id"]: match for match in potential_matches}

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

            # Проверяем, есть ли взаимный лайк
            mutual_like = db.query(Like).filter(
                Like.user_id == user.id,
                Like.liked_user_id == current_user_id
            ).first()
            mutual = mutual_like is not None

            match = match_info.get(user.id)
            if match:
                interests_percentage = (match["common_interests_count"] / len(
                    current_user.interests
                    )) * 100 if current_user.interests else 0
                distance_percentage = 100 if match["distance"] and str(match["distance"]) <= MAX_DISTANCE else 0
                match_percentage = (interests_percentage + distance_percentage) / 2
            else:
                match_percentage = 0  # or some default value

            # Now include the match_percentage in the response
            response.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "avatar_url": avatar_url[0] if avatar_url else None,
                    "date_of_birth": user.date_of_birth,
                    "city_name": city_name[0] if city_name else None,
                    "is_favorite": True,
                    "about_me": user.about_me,
                    "status": user.status,
                    "mutual": mutual,
                    "match_percentage": match_percentage  # Added match_percentage here
                }
            )
        return response



@router.get("/liked_me", response_model=List[UserLikesResponse], summary="Список пользователей, лайкнувших меня")
def get_liked_by(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)
        current_user = db.query(User).options(joinedload(User.interests)).filter(User.id == current_user_id).first()
        liked_by_users = db.query(User).join(Like, User.id == Like.user_id).filter(
            Like.liked_user_id == current_user_id).all()

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
            GROUP BY d.potential_match_id, d.first_name, d.date_of_birth, d.gender, d.city_id, d.distance
            """, params={"current_user_id": current_user_id}
        )

        match_info = {match["potential_match_id"]: match for match in potential_matches}

        response = []
        for user in liked_by_users:
            avatar_url = db.query(UserPhoto.photo_url).filter(
                UserPhoto.user_id == user.id, UserPhoto.is_avatar == True).first()
            city_name_tuple = db.query(City.city_name).filter(City.id == user.city_id).first()
            city_name = city_name_tuple[0] if city_name_tuple else None

            # Проверяем, есть ли взаимный лайк
            mutual_like = db.query(Like).filter(
                Like.user_id == current_user_id,
                Like.liked_user_id == user.id
            ).first()
            mutual = mutual_like is not None

            # Проверяем, находится ли пользователь в списке избранных текущего пользователя
            is_favorite = db.query(Favorite).filter(
                Favorite.user_id == current_user_id,
                Favorite.favorite_user_id == user.id
            ).first() is not None

            match = match_info.get(user.id)
            if match:
                interests_count = len(current_user.interests) if current_user.interests else 0
                interests_percentage = (match[
                                            "common_interests_count"] / interests_count) * 100 if interests_count > 0 else 0
                distance = float(match["distance"]) if match["distance"] else 0
                distance_percentage = 100 if distance and distance <= MAX_DISTANCE else 0
                match_percentage = (interests_percentage + distance_percentage) / 2
            else:
                match_percentage = 0  # or some default value

            response.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "avatar_url": avatar_url[0] if avatar_url else None,
                    "date_of_birth": user.date_of_birth,
                    "city_name": city_name,
                    "is_favorite": is_favorite,
                    "about_me": user.about_me,
                    "status": user.status,
                    "mutual": mutual,
                    "match_percentage": match_percentage
                }
            )
        return response




@router.get("/liked_users", response_model=List[UserLikesResponse], summary="Список пользователей, которых лайкнул я")
def get_liked_users(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token)
        current_user = db.query(User).options(joinedload(User.interests)).filter(User.id == current_user_id).first()

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
            GROUP BY d.potential_match_id, d.first_name, d.date_of_birth, d.gender, d.city_id, d.distance
            """, params={"current_user_id": current_user_id}
        )

        match_info = {match["potential_match_id"]: match for match in potential_matches}

        # Запрос на получение пользователей, которых текущий пользователь лайкнул
        liked_users = db.query(User).join(Like,
                                          User.id == Like.liked_user_id).filter(Like.user_id == current_user_id).all()

        response = []
        for user in liked_users:
            avatar_url = db.query(UserPhoto.photo_url).filter(UserPhoto.user_id == user.id,
                                                              UserPhoto.is_avatar == True).first()
            city_name = db.query(City.city_name).filter(City.id == user.city_id).first()

            # Проверяем, есть ли взаимный лайк
            mutual_like = db.query(Like).filter(Like.user_id == user.id, Like.liked_user_id == current_user_id).first()
            mutual = mutual_like is not None

            # Проверяем, находится ли пользователь в списке избранных текущего пользователя
            is_favorite = db.query(Favorite).filter(Favorite.user_id == current_user_id,
                                                    Favorite.favorite_user_id == user.id).first() is not None

            match = match_info.get(user.id)
            if match:

                interests_count = len(current_user.interests) if current_user.interests else 0
                interests_percentage = (match["common_interests_count"] /
                                        interests_count) * 100 if interests_count > 0 else 0
                distance = float(match["distance"]) if match["distance"] else 0
                distance_percentage = 100 if distance and distance <= MAX_DISTANCE else 0
                match_percentage = (interests_percentage + distance_percentage) / 2
            else:
                match_percentage = 0  # or some default value

            response.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "avatar_url": avatar_url[0] if avatar_url else None,
                    "date_of_birth": user.date_of_birth,
                    "city_name": city_name[0] if city_name else None,
                    "is_favorite": is_favorite,
                    "about_me": user.about_me,
                    "status": user.status,
                    "mutual": mutual,
                    "match_percentage": match_percentage
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
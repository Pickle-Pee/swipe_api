from datetime import date

from fastapi import HTTPException, APIRouter, Depends, Query
from typing import List
from common.models import User, UserPhoto, City, Like
from common.schemas import MatchResponse
from common.utils import execute_sql
from common.utils.auth_utils import get_token, get_user_id_from_token
from common.utils.enum_mapping import SMOKING_ATTITUDE_MAP, ALCOHOL_ATTITUDE_MAP, CHILDREN_PREFERENCE_MAP, \
    WHAT_LOOKING_FOR_MAP, APPEARANCE_MAP, RELIGION_MAP
from config import SessionLocal

router = APIRouter(prefix="/match", tags=["Matches Controller"])


@router.get("/find_matches", response_model=List[MatchResponse])
def find_matches(
    access_token: str = Depends(get_token),
    minAge: int = Query(None),
    maxAge: int = Query(None),
    minHeight: int = Query(None),
    maxHeight: int = Query(None),
    city: str = Query(None),
    smokingAttitude: str = Query(None),
    alcoholAttitude: str = Query(None),
    childrenPreference: str = Query(None),
    whatLookingFor: str = Query(None),
    appearance: str = Query(None),
    religion: str = Query(None)
):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user or not current_user.city_id or not current_user.gender:
            raise HTTPException(status_code=404, detail="User not found or profile incomplete")

        # Рассчёт возраста текущего пользователя
        today = date.today()
        user_age = today.year - current_user.date_of_birth.year - (
            (today.month, today.day) < (current_user.date_of_birth.month, current_user.date_of_birth.day)
        )
        if user_age < 18:
            return []

        # Диапазон возраста по умолчанию
        if minAge is None and maxAge is None:
            default_min_age = max(18, user_age - 10)
            default_max_age = user_age + 10
        else:
            default_min_age = max(18, minAge if minAge is not None else 18)
            default_max_age = maxAge if maxAge is not None else (user_age + 5)

        target_city_id = current_user.city_id
        if city:
            city_obj = db.query(City).filter(City.city_name == city).first()
            if city_obj:
                target_city_id = city_obj.id

        params = {
            "current_user_id": user_id,
            "min_age": default_min_age,
            "max_age": default_max_age,
            "filter_city_id": target_city_id
        }

        # Условия для u2
        u2_conditions = []
        # Возраст
        u2_conditions.append("""u2.date_of_birth 
            BETWEEN CURRENT_DATE - make_interval(years => :max_age)
            AND CURRENT_DATE - make_interval(years => :min_age)
        """)
        # Город
        u2_conditions.append("u2.city_id = :filter_city_id")

        # Формируем условия для user_attributes (если заданы фильтры)
        ua2_conditions = []
        if minHeight is not None:
            ua2_conditions.append("ua2.height >= :minHeight")
            params["minHeight"] = minHeight
        if maxHeight is not None:
            ua2_conditions.append("ua2.height <= :maxHeight")
            params["maxHeight"] = maxHeight

        # Курение
        if smokingAttitude is not None:
            db_value = SMOKING_ATTITUDE_MAP.get(smokingAttitude)
            if db_value is None:
                raise HTTPException(status_code=400, detail="Invalid smoking attitude value")
            ua2_conditions.append("ua2.smoking_attitude = :smoking_attitude")
            params["smoking_attitude"] = db_value

        # Алкоголь
        if alcoholAttitude is not None:
            db_value = ALCOHOL_ATTITUDE_MAP.get(alcoholAttitude)
            if db_value is None:
                raise HTTPException(status_code=400, detail="Invalid alcohol attitude value")
            ua2_conditions.append("ua2.alcohol_attitude = :alcohol_attitude")
            params["alcohol_attitude"] = db_value

        # Дети
        if childrenPreference is not None:
            db_value = CHILDREN_PREFERENCE_MAP.get(childrenPreference)
            if db_value is None:
                raise HTTPException(status_code=400, detail="Invalid children preference value")
            ua2_conditions.append("ua2.children_preference = :children_preference")
            params["children_preference"] = db_value

        # Цель знакомства
        if whatLookingFor is not None:
            db_value = WHAT_LOOKING_FOR_MAP.get(whatLookingFor)
            if db_value is None:
                raise HTTPException(status_code=400, detail="Invalid what looking for value")
            ua2_conditions.append("ua2.what_looking_for = :what_looking_for")
            params["what_looking_for"] = db_value

        # Внешность
        if appearance is not None:
            db_value = APPEARANCE_MAP.get(appearance)
            if db_value is None:
                raise HTTPException(status_code=400, detail="Invalid appearance value")
            ua2_conditions.append("ua2.appearance = :appearance")
            params["appearance"] = db_value

        # Религия
        if religion is not None:
            db_value = RELIGION_MAP.get(religion)
            if db_value is None:
                raise HTTPException(status_code=400, detail="Invalid religion value")
            ua2_conditions.append("ua2.religion = :religion")
            params["religion"] = db_value

        # Если есть ua2_conditions => JOIN user_attributes
        attribute_join = ""
        if ua2_conditions:
            attribute_join = "JOIN user_attributes ua2 ON ua2.user_id = u2.id AND " + " AND ".join(ua2_conditions)

        where_clause = ""
        if u2_conditions:
            where_clause = " AND " + " AND ".join(u2_conditions)

        # ВАЖНО: исключаем всех, кто уже в лайках или дизлайках текущего пользователя
        exclusion_subquery = """
        AND u2.id NOT IN (
            SELECT liked_user_id FROM likes WHERE user_id = :current_user_id
            UNION
            SELECT disliked_user_id FROM dislikes WHERE user_id = :current_user_id
        )
        """

        query = f"""
        SELECT
            u2.id AS potential_match_id,
            u2.first_name,
            u2.date_of_birth,
            u2.gender,
            u2.city_id
        FROM users u1
        JOIN users u2
            ON u1.id != u2.id
            AND u1.gender != u2.gender
            AND u2.deleted = false
            AND u2.verify != 'denied'
            AND u2.phone_number NOT IN ('79104263221', '79108983207', '79000000000', '79040660775')
        {attribute_join}
        WHERE u1.id = :current_user_id
        {where_clause}
        {exclusion_subquery}
        LIMIT 5
        """

        print("Generated SQL:")
        print(query)
        print("Params:", params)

        potential_matches = execute_sql(query, params)

        response = []
        for match in potential_matches:
            pm_id = match["potential_match_id"]

            # 1) Смотрим, есть ли запись mutual=True в likes
            like_obj = db.query(Like).filter(
                Like.mutual == True,
                (
                        ((Like.user_id == user_id) & (Like.liked_user_id == pm_id)) |
                        ((Like.user_id == pm_id) & (Like.liked_user_id == user_id))
                )
            ).first()
            is_mutual = (like_obj is not None)

            # 2) Определяем avatar_url, match_percentage и т.п.
            avatar_query = db.query(UserPhoto.photo_url).filter(
                UserPhoto.user_id == pm_id,
                UserPhoto.is_avatar == True
            ).first()
            avatar_url = avatar_query[0] if avatar_query else None

            match_percentage = 0
            interests_list = []

            response.append(
                MatchResponse(
                    user_id=match["potential_match_id"],
                    first_name=match["first_name"],
                    date_of_birth=match["date_of_birth"],
                    gender=match["gender"],
                    city_name=db.query(City.city_name).filter(City.id == match["city_id"]).first()[0]
                               if match["city_id"] else None,
                    interests=interests_list,
                    avatar_url=avatar_url,
                    match_percentage=match_percentage,
                    is_favorite=False
                )
            )

        return response

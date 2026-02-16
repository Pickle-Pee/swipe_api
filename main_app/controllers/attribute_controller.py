from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict

from common.models.enums import AppearanceEnum, SmokingAttitudeEnum, AlcoholAttitudeEnum, WhatLookingForEnum, \
    ReligionEnum, ChildrenEnum
from common.models.user_models import UserAttributes, User
from common.schemas.service_schemas import EnumItem
from common.schemas.user_schemas import AddUserAttributesRequest, UserAttributesResponse
from common.utils import get_token, get_user_id_from_token
from config import SessionLocal, logger

router = APIRouter(
    prefix="/attributes",
    tags=["Enums"],
    responses={404: {"description": "Not found"}}
)


@router.get("/", response_model=Dict[str, List[EnumItem]], summary="Получение всех перечислений")
async def get_all_attributes():
    try:
        return {
            "appearance": [{"name": e.name, "description": e.value} for e in AppearanceEnum],
            "smoking_attitude": [{"name": e.name, "description": e.value} for e in SmokingAttitudeEnum],
            "alcohol_attitude": [{"name": e.name, "description": e.value} for e in AlcoholAttitudeEnum],
            "what_looking_for": [{"name": e.name, "description": e.value} for e in WhatLookingForEnum],
            "religion": [{"name": e.name, "description": e.value} for e in ReligionEnum],
            "children_preference": [{"name": e.name, "description": e.value} for e in ChildrenEnum],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ошибка при получении данных перечислений")


@router.get("/user_attributes", summary="Получение аттрибутов пользователя")
async def get_user_attributes(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user_attributes = db.query(UserAttributes).filter(UserAttributes.user_id == user_id).one_or_none()

        if user_attributes is None:
            raise HTTPException(status_code=404, detail="Атрибуты пользователя не найдены")

        return user_attributes


@router.post("/add_attributes", summary="Добавление аттрибутов пользователя")
async def add_user_attributes(request: AddUserAttributesRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            # Получение существующих атрибутов или создание новых
            user_attributes = db.query(UserAttributes).filter(UserAttributes.user_id == user_id).one_or_none()
            if not user_attributes:
                user_attributes = UserAttributes(user_id=user_id)
                db.add(user_attributes)

            # Обновление полей атрибутов
            for field, value in request.dict(exclude_unset=True).items():
                setattr(user_attributes, field, value)

            db.commit()
            db.refresh(user_attributes)

            return user_attributes

        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error updating user attributes: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.put("/update_attributes", response_model=UserAttributesResponse, summary="Обновление атрибутов пользователя")
async def update_user_attributes(request: AddUserAttributesRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).one_or_none()

            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            # Получение существующих атрибутов
            user_attributes = db.query(UserAttributes).filter(UserAttributes.user_id == user_id).one_or_none()
            if not user_attributes:
                raise HTTPException(status_code=404, detail="Атрибуты пользователя не найдены. Сначала добавьте их.")

            # Обновление полей атрибутов
            for field, value in request.dict(exclude_unset=True).items():
                setattr(user_attributes, field, value)

            db.commit()
            db.refresh(user_attributes)

            return user_attributes

        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error updating user attributes: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

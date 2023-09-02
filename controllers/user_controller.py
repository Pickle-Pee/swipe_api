from fastapi import HTTPException, APIRouter, Depends
from typing import List
from config import SessionLocal, SECRET_KEY
from models.user_models import User
from schemas.user_schemas import UserDataResponse
from utils.auth_utils import get_token, get_user_id_from_token
import traceback


router = APIRouter(prefix="/user", tags=["User Controller"])


@router.get("/", response_model=UserDataResponse, summary="Получение информации о пользователе")
def get_user(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token, SECRET_KEY)
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user_data = {
                    "id": user.id,
                    "phone_number": user.phone_number,
                    "first_name": user.first_name if user.first_name else None,
                    "last_name": user.last_name if user.last_name else None,
                    "date_of_birth": user.date_of_birth if user.date_of_birth else None,
                    "gender": user.gender if user.gender else None,
                    "verify": user.verify,
                    "is_subscription": user.is_subscription
                }
                return user_data
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




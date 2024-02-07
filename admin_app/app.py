import os
from typing import List

from fastapi import Depends, HTTPException, FastAPI
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import joinedload
from starlette import status
from common.models import User, Interest, Subscription
from common.schemas import UsersResponse, UserResponseAdmin, InterestResponse, SubscriptionCreate, SubscriptionSchema
from common.utils import get_admin_by_username, create_access_token
from common.utils.auth_utils import verify_password
from config import SessionLocal
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.post("/admin/login", summary="Авторизация администратора")
async def login_admin(form_data: OAuth2PasswordRequestForm = Depends()):
    with SessionLocal() as db:
        admin = get_admin_by_username(db, username=form_data.username)

        if not admin or not verify_password(form_data.password, admin.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Создаем токен доступа для администратора
        access_token = create_access_token(data={"sub": admin.username, "admin_id": admin.id})
        return {"access_token": access_token, "token_type": "bearer"}


# @app.post("/admin/delete", summary="Авторизация администратора")
# async def login_admin(form_data: OAuth2PasswordRequestForm = Depends()):
#     with SessionLocal() as db:
#         admin = get_admin_by_username(db, username=form_data.username)
#
#         if not admin or not verify_password(form_data.password, admin.hashed_password):
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Incorrect username or password",
#                 headers={"WWW-Authenticate": "Bearer"},
#             )
#
#         # Создаем токен доступа для администратора
#         access_token = create_access_token(data={"sub": admin.username, "admin_id": admin.id})
#         return {"access_token": access_token, "token_type": "bearer"}


@app.get("/admin/users", response_model=UsersResponse, summary="Получение списка всех пользователей")
async def get_all_users():
    with SessionLocal() as db:
        db_users = db.query(User).options(joinedload(User.city)).all()
        if not db_users:
            raise HTTPException(status_code=404, detail="Users not found")

        users = []
        for user in db_users:
            user_dict = {
                "id": user.id,
                "phone_number": user.phone_number,
                "first_name": user.first_name or None,
                "last_name": user.last_name or None,
                "date_of_birth": user.date_of_birth or None,
                "gender": user.gender or None,
                "city_name": user.city.city_name if user.city else None,
                "deleted": user.deleted or None
            }
            users.append(user_dict)

        return UsersResponse(users=users)


@app.get("/admin/user/{user_id}", response_model=UserResponseAdmin, summary="Получение информации о конкретном пользователе")
async def get_user_info(user_id: int):
    with SessionLocal() as db:
        db_user = db.query(User).options(joinedload(User.city)).filter(User.id == user_id).first()
        if db_user is None:
            raise HTTPException(status_code=404, detail="User not found")

        return db_user


@app.get("/admin/interests_list", summary="Получение списка доступных интересов", response_model=InterestResponse)
async def get_interests_list():
    with SessionLocal() as db:
        interests = db.query(Interest).all()
        if not interests:
            raise HTTPException(status_code=404, detail="No interests found")

        interests_list = [{"id": interest.id, "interest_text": interest.interest_text} for interest in interests]

        return {"interests": interests_list}


@app.get("/admin/subscriptions", response_model=List[SubscriptionSchema])
def read_subscriptions(skip: int = 0, limit: int = 100):
    with SessionLocal() as db:
        subscriptions = db.query(Subscription).offset(skip).limit(limit).all()

    return subscriptions


@app.post("/admin/create_subscription", response_model=SubscriptionSchema)
def create_subscription(subscription: SubscriptionCreate):
    with SessionLocal() as db:
        db_subscription = Subscription(**subscription.dict())
        db.add(db_subscription)
        db.commit()
        db.refresh(db_subscription)

    return db_subscription


@app.delete("/admin/delete_subscription/{subscription_id}", response_model=SubscriptionSchema)
def delete_subscription(subscription_id: int):
    with SessionLocal() as db:
        db_subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if db_subscription is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        db.delete(db_subscription)
        db.commit()

    return db_subscription


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(app, host=app_host, port=1027)

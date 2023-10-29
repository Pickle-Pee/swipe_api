import os

from fastapi import Depends, HTTPException, FastAPI
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import joinedload

from common.models import User
from common.schemas import UsersResponse
from common.utils import get_admin_by_username, security
from config import SessionLocal

app = FastAPI()

origins = ["*"]

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

        if not admin or not security.verify_password(form_data.password, admin.hashed_password):
            raise HTTPException(
                status_code=401,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = security.create_access_token(data={"sub": admin.username, "admin_id": admin.id})
        return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users", response_model=UsersResponse)
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
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "first_name": user.first_name or None,
                "last_name": user.last_name or None,
                "date_of_birth": user.date_of_birth or None,
                "gender": user.gender or None,
                "verify": user.verify,
                "is_subscription": user.is_subscription,
                "city_name": user.city.city_name if user.city else None,
                "about_me": user.about_me or None,
                "status": user.status or None,
                "deleted": user.deleted or None
            }
            users.append(user_dict)

        return UsersResponse(users=users)


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(app, host=app_host, port=1027)

import os

from fastapi import Depends, HTTPException, FastAPI
from fastapi.security import OAuth2PasswordRequestForm

from common.models import User
from common.schemas import PersonalUserDataResponse
from common.utils import get_admin_by_username, security
from config import SessionLocal

app = FastAPI()


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


@app.get("/users", response_model=PersonalUserDataResponse)
async def get_all_users():
    with SessionLocal() as db:
        users = db.query(User).all()
        if not users:
            raise HTTPException(status_code=404, detail="Users not found")
        return PersonalUserDataResponse(users=users)

if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(app, host=app_host, port=1027)

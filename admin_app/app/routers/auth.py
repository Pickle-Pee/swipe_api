from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from common.models import Admin
from .. import schemas
from ..dependencies import authenticate_admin, create_access_token, get_db, get_password_hash

router = APIRouter(
    tags=["auth"],
)


@router.post("/token", response_model=schemas.Token, summary="Получение JWT токена для администратора")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = authenticate_admin(db, form_data.username, form_data.password)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неправильные имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": admin.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=schemas.Token, summary="Логин администратора")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return login_for_access_token(form_data, db)


@router.post("/register", response_model=schemas.AdminResponse, summary="Регистрация нового администратора")
def register_admin(admin: schemas.AdminCreate, db: Session = Depends(get_db)):
    db_admin = db.query(Admin).filter(
        (Admin.username == admin.username) | (Admin.email == admin.email)).first()
    if db_admin:
        raise HTTPException(status_code=400, detail="Имя пользователя или email уже используются")
    hashed_password = get_password_hash(admin.password)
    new_admin = Admin(
        username=admin.username,
        email=admin.email,
        hashed_password=hashed_password
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin

from fastapi import HTTPException, Header
from datetime import datetime, timedelta
from config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_HOURS
import re
import jwt


def create_jwt_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm="HS256")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return create_jwt_token(to_encode)


# Пример функции генерации refresh token
def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return create_jwt_token(to_encode)


# Пример функции обновления токена
def refresh_token(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms="HS256")
        new_access_token = create_access_token({"sub": payload["sub"]})
        return {"access_token": new_access_token}
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный refresh token")


def get_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split()[1]
    return token


def validate_phone_number(phone_number: str):
    if not re.match(r'^\d{11}$', phone_number):
        return False

    if phone_number[0] != '7':
        return False

    return True


def get_user_id_from_token(access_token: str):
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=["HS256"])
        print("Decoded payload:", payload)
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=400, detail="User ID not found")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")

    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


import json
import os
import random
import requests
from fastapi import HTTPException, Header
from datetime import datetime, timedelta
from config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_HOURS, VERIFY_SEND_TEXT
import re
import jwt
from config import VERIFY_CHAT_ID, VERIFY_CHAT_LINK
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет, совпадает ли предоставленный пароль с его хешированным вариантом.

    :param plain_password: Пароль в открытом виде, который нужно проверить
    :param hashed_password: Хешированный пароль для сравнения
    :return: True если пароли совпадают, иначе False
    """
    return pwd_context.verify(plain_password, hashed_password)

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


def send_text_message(user_id, first_name):
    data = {
        "chat_id": f"{VERIFY_CHAT_ID}",
        "text": f"Пользователь: {user_id}\nИмя: {first_name}",
    }
    response = requests.post(VERIFY_SEND_TEXT, data=data)
    if response.status_code != 200:
        print("Error sending text message:", response.status_code)
        print(response.text)

def send_photos_to_bot(user_id, first_name, photo_paths):
    send_text_message(user_id, first_name)
    media = [
        {
            "type": "photo",
            "media": f"attach://{os.path.basename(photo_path)}"
        }
        for photo_path in photo_paths
    ]
    files = [(os.path.basename(photo_path), (os.path.basename(photo_path), open(photo_path, "rb"))) for photo_path in photo_paths]

    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            files.append((os.path.basename(photo_path), (os.path.basename(photo_path), open(photo_path, "rb"))))
        else:
            print(f"File {photo_path} does not exist.")

    data = {
        "chat_id": f"{VERIFY_CHAT_ID}",
        "media": json.dumps(media),
    }

    response = requests.post(VERIFY_CHAT_LINK, data=data, files=files)

    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            os.remove(photo_path)

    if response.status_code != 200:
        print("Error:", response.status_code)
        print(response.text)

    return response.json()


def generate_verification_code(length=6):
    """Generate a random verification code of the specified length."""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])
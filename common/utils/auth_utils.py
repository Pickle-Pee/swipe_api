import random
from fastapi import HTTPException, Header
from datetime import datetime, timedelta
from config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_HOURS
import re
import jwt
import logging
from passlib.context import CryptContext
import face_recognition
from PIL import Image, ExifTags


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
        if payload.get("token_type") != "refresh":
            raise HTTPException(status_code=400, detail="Invalid token type")

        new_access_token = create_access_token({"sub": payload["sub"]})

        # Генерация нового refresh токена, если требуется
        new_refresh_token = create_refresh_token({"sub": payload["sub"], "token_type": "refresh"})

        logger.info("Successfully refreshed tokens")

        return {"access_token": new_access_token, "refresh_token": new_refresh_token}
    except jwt.ExpiredSignatureError:
        logger.error("Expired refresh token")
        raise HTTPException(status_code=401, detail="Expired refresh token")
    except jwt.DecodeError:
        logger.error("Invalid token during refresh")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error in refresh_token: {str(e)}")
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
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=400, detail="User ID not found")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")

    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def compare_faces(profile_photo_content, selfie_content):
    # Загрузка изображений из файлового потока
    profile_image = face_recognition.load_image_file(profile_photo_content)
    selfie_image = face_recognition.load_image_file(selfie_content)

    # Извлечение фичей лиц
    profile_encoding = face_recognition.face_encodings(profile_image)
    selfie_encoding = face_recognition.face_encodings(selfie_image)

    # Если на одном из изображений не удалось найти лицо
    if len(profile_encoding) == 0 or len(selfie_encoding) == 0:
        return False, 1.0  # Лица не найдены

    # Сравнение лиц
    results = face_recognition.compare_faces([profile_encoding[0]], selfie_encoding[0])
    face_distance = face_recognition.face_distance([profile_encoding[0]], selfie_encoding[0])

    # Определение результата
    return bool(results[0] and face_distance[0] < 0.6), float(face_distance[0])


def correct_orientation(image_path):
    image = Image.open(image_path)
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = image._getexif()
        if exif is not None:
            orientation = exif.get(orientation)

            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
        image.save(image_path)
    except (AttributeError, KeyError, IndexError):
        pass
    return image_path


def generate_verification_code(length=6):
    """Generate a random verification code of the specified length."""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

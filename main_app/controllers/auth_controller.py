import os
import traceback
from datetime import datetime

import magic

from fastapi import HTTPException, status, APIRouter, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func

from common.models.auth_models import TemporaryCode, RefreshToken
from common.models.cities_models import City, Region
from common.models.user_models import User, VerificationQueue
from common.models.error_models import ErrorResponse
from common.schemas.auth_schemas import TokenResponse, CheckCodeResponse, VerificationResponse
from common.schemas.user_schemas import UserCreate, UserIdResponse
from common.utils.service_utils import verify_token
from config import SECRET_KEY, logger
from common.utils.auth_utils import create_refresh_token, create_access_token, validate_phone_number, get_token, \
    get_user_id_from_token, send_photos_to_bot
import jwt
from config import s3_client, SessionLocal, BUCKET_VERIFY_IMAGES


router = APIRouter(prefix="/auth", tags=["Auth Controller"])


@router.post("/refresh_token", response_model=TokenResponse)
def get_refreshed_token(refresh_token: str):
    with SessionLocal() as db:
        try:
            decoded_refresh_token = jwt.decode(refresh_token, SECRET_KEY, algorithms=["HS256"])
            if decoded_refresh_token.get("token_type") != "refresh":
                raise HTTPException(status_code=400, detail="Invalid refresh token")

            phone_number = decoded_refresh_token.get("sub")
            user = db.query(User).filter_by(phone_number=phone_number).first()
            if not user:
                raise HTTPException(status_code=400, detail="User not found")
            # Генерация нового Refresh токена
            new_refresh_token_data = {"sub": phone_number, "token_type": "refresh"}
            new_refresh_token = create_refresh_token(new_refresh_token_data)

            # Обновление Refresh токена в базе данных
            user.refresh_tokens.refresh_token = new_refresh_token
            db.commit()

            new_token_data = {
                "sub": phone_number,
                "user_id": user.id
            }
            new_access_token = create_access_token(new_token_data)

            return TokenResponse(access_token=f"Bearer {new_access_token}", refresh_token=new_refresh_token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Expired refresh token")
        except jwt.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid token")


@router.post(
    "/check_code", summary="Проверка кода авторизации", response_model=CheckCodeResponse,
    responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}}
)
def check_verification_code(phone_number: str, verification_code: str):
    with SessionLocal() as db:
        try:
            # Проверяем совпадение номера и кода
            query = db.query(TemporaryCode).filter_by(phone_number=phone_number, code=verification_code).first()
            if query:
                return JSONResponse(content={"message": "Код авторизации подтвержден."}, status_code=status.HTTP_200_OK)
            else:
                error_response = ErrorResponse(detail="Неверный код авторизации.", code=604)
                return JSONResponse(content=error_response.dict(), status_code=400)

        except Exception as e:
            print("Error checking verification code:", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Error checking verification code")


@router.post("/check_phone", summary="Валидация номера телефона")
def validate_phone(phone_number: str):
    with SessionLocal() as db:
        try:

            if not validate_phone_number(phone_number):
                error_response = ErrorResponse(detail="Некорректный номер телефона", code=666)
                return JSONResponse(content=error_response.dict(), status_code=400)

            # Проверяем, зарегистрирован ли номер телефона
            query = db.query(User).filter_by(phone_number=phone_number).first()
            if query:
                error_response = ErrorResponse(detail="Пользователь зарегистрирован.", code=612)
                return JSONResponse(content=error_response.dict(), status_code=400)

        except Exception as e:
            print("Error validating phone number:", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Error validating phone number")


@router.post(
    "/send_code", summary="Отправка кода авторизации", responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_200_OK: {"model": VerificationResponse}
    }
)
def send_verification_code(phone_number: str):
    with SessionLocal() as db:
        try:

            if not validate_phone_number(phone_number):
                error_response = ErrorResponse(detail="Некорректный номер телефона", code=666)
                return JSONResponse(content=error_response.dict(), status_code=400)

            verification_code = "000000"
            temp_code = TemporaryCode(phone_number=phone_number, code=verification_code)
            db.add(temp_code)
            db.commit()

            return VerificationResponse(verification_code=verification_code)
        except Exception as e:
            print("Error sending verification code:", e)
            raise HTTPException(status_code=500, detail="Error sending verification code")


@router.post("/register", response_model=TokenResponse, summary="Регистрация пользователя")
def register(user_data: UserCreate):
    with SessionLocal() as db:
        try:
            existing_user = db.query(User).filter_by(phone_number=user_data.phone_number).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Phone number already registered")

            stored_code = db.query(TemporaryCode).filter_by(phone_number=user_data.phone_number).first()
            if not stored_code:
                raise HTTPException(status_code=400, detail="Invalid verification code")

            if ' (' in user_data.city_name:
                city_name, region_name = user_data.city_name.rsplit(' (', 1)
                region_name = region_name.rstrip(')')
            else:
                city_name = user_data.city_name.strip()
                region_name = None

            city = db.query(City) \
                .join(Region, City.region_id == Region.id) \
                .filter(func.lower(City.city_name) == city_name.lower()) \
                .filter(func.lower(Region.name) == region_name.lower() if region_name else True) \
                .first()

            if not city and region_name:
                city = db.query(City) \
                    .filter(func.lower(City.city_name) == city_name.lower()) \
                    .first()

            if not city:
                raise HTTPException(status_code=404, detail="City not found")

            city_id = city.id

            new_user = User(
                phone_number=user_data.phone_number,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                date_of_birth=user_data.date_of_birth,
                gender=user_data.gender,
                city_id=city_id,
                is_subscription=False
            )
            db.add(new_user)
            db.commit()

            token_data = {"sub": new_user.phone_number, "user_id": new_user.id, "verify": new_user.verify}
            access_token = create_access_token(token_data)

            refresh_token_data = {"sub": new_user.phone_number, "token_type": "refresh"}
            refresh_token = create_refresh_token(refresh_token_data)

            db_refresh_token = RefreshToken(user_id=new_user.id, refresh_token=refresh_token)
            db.add(db_refresh_token)
            db.commit()

            db.delete(stored_code)
            db.commit()

            token_response = TokenResponse(access_token=f"Bearer {access_token}", refresh_token=refresh_token)
            return token_response

        except HTTPException as he:
            raise he
        except Exception as e:
            print("Error registering user:", e)
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Error registering user")


@router.post("/login", response_model=TokenResponse, summary="Авторизация пользователя")
def login(phone_number: str, code: str):
    with SessionLocal() as db:
        try:

            if not validate_phone_number(phone_number):
                return JSONResponse(
                    content={"message": "Некорректный номер телефона", "code": 666},
                    status_code=status.HTTP_400_BAD_REQUEST)

            # Проверка кода в базе данных
            stored_code = db.query(TemporaryCode).filter_by(phone_number=phone_number, code=code).first()
            if not stored_code:
                raise HTTPException(status_code=400, detail="Invalid verification code")

            # Получение user_id по номеру телефона из таблицы users
            user = db.query(User).filter_by(phone_number=phone_number).first()
            if not user:
                raise HTTPException(status_code=400, detail="User not found")

            # Генерация токена для авторизации
            token_data = {"sub": phone_number, "user_id": user.id, "verify": user.verify}
            access_token = create_access_token(token_data)

            # Генерация Refresh токена
            refresh_token_data = {"sub": phone_number, "token_type": "refresh"}
            refresh_token = create_refresh_token(refresh_token_data)

            # Проверяем, есть ли запись с токеном для данного пользователя
            existing_refresh_token = db.query(RefreshToken).filter_by(user_id=user.id).first()

            if existing_refresh_token:
                existing_refresh_token.refresh_token = refresh_token  # Обновляем Refresh токен
            else:
                # Создаем новую запись Refresh токена
                db_refresh_token = RefreshToken(user_id=user.id, refresh_token=refresh_token)
                db.add(db_refresh_token)

            db.commit()

            db.delete(stored_code)
            db.commit()

            token_response = TokenResponse(access_token=f"Bearer {access_token}", refresh_token=refresh_token)

            return token_response
        except HTTPException as he:
            raise he
        except Exception as e:
            print("Error logging in:", e)
            raise HTTPException(status_code=500, detail="Error logging in")


@router.get("/whoami", response_model=UserIdResponse, summary="Получение id пользователя по access-token")
def who_am_i(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Invalid token")

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="Пользователь не найден")



@router.post("/upload_verify_photos")
async def upload_verify_photos(
        access_token: str = Depends(get_token),
        profile_photo: UploadFile = File(...),
        verification_selfie: UploadFile = File(...)):
    logger.info("Received request to upload verification photos")

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"User with id {user_id} not found")
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"User with id {user_id} found")
        first_name = user.first_name
        db.commit()

    photos = [profile_photo, verification_selfie]
    photo_keys = []

    for index, photo in enumerate(photos):
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(photo.file.read(1024))
        photo.file.seek(0)  # reset the file cursor to the beginning

        # Map MIME types to file extensions
        mime_to_ext = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/bmp": "bmp",
            "image/tiff": "tiff",
            "image/webp": "webp",
            "image/heic": "heic",
            "image/heif": "heif",
        }

        extension = mime_to_ext.get(mime_type)
        if extension is None:
            logger.error(f"Unsupported file type {mime_type}")
            raise HTTPException(status_code=400, detail="Unsupported file type")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"verification_{user_id}_{timestamp}_{index}.{extension}"

        logger.info(f"Uploading file {file_name}")

        try:
            # Always write the file to the buffer before uploading to S3
            with open(file_name, "wb") as buffer:
                buffer.write(photo.file.read())

            # Upload the file to S3
            with open(file_name, "rb") as f:
                s3_client.upload_fileobj(f, BUCKET_VERIFY_IMAGES, file_name)

            photo_keys.append(file_name)
            logger.info(f"File {file_name} uploaded successfully to S3")
        except Exception as e:
            logger.error(f"Failed to upload file {file_name} to S3: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload file")

        logger.info(f"Photo keys: {photo_keys}")

    send_photos_to_bot(user_id, first_name, photo_keys)

    # Clean up the local files
    for file_name in photo_keys:
        if os.path.exists(file_name):
            os.remove(file_name)
            logger.info(f"Local file {file_name} removed")

    with SessionLocal() as db:
        photo_urls = [f"/service/get_file/{key}" for key in photo_keys]
        verification_record = VerificationQueue(
            user_id=user_id,
            photo1=photo_urls[0],
            photo2=photo_urls[1],
            status='pending'
        )
        db.add(verification_record)
        db.commit()

    return {"status": "photos received, uploaded to Yandex Cloud, and sent to bot"}


@router.post('/set_verify/{user_id}')
def verify_user_in_bot(user_id: int, status: str, authorization: HTTPAuthorizationCredentials = Depends(verify_token)):
    with SessionLocal() as db:
        verification = db.query(VerificationQueue).filter(VerificationQueue.user_id == user_id).first()

        if not verification:
            raise HTTPException(status_code=404, detail="User not found in verification queue")

        verification.status = status
        db.commit()

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if status == "approved":
            user.verify = "access"
        elif status == "denied":
            user.verify = "denied"
        else:
            raise HTTPException(status_code=400, detail="Invalid status")

        db.commit()

        return {"status": "success"}
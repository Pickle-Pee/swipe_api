import os
import traceback
from datetime import datetime
import magic
from fastapi.responses import JSONResponse
from sqlalchemy import func
import jwt
import logging
import httpx
from fastapi import (
    HTTPException,
    status,
    APIRouter,
    Depends,
    UploadFile,
    File
)
from common.models import (
    TemporaryCode,
    RefreshToken,
    City,
    Region,
    User,
    VerificationQueue,
    ErrorResponse,
    UserPhoto
)
from common.schemas import (
    TokenResponse,
    CheckCodeResponse,
    VerificationResponse,
    UserCreate,
    UserIdResponse
)

from common.utils import (
    create_refresh_token,
    create_access_token,
    validate_phone_number,
    get_token,
    get_user_id_from_token,
    generate_verification_code,
    convert_to_jpeg,
    compare_faces,
    correct_orientation)
from common.utils.smsc_api import SMSC
from config import (
    SECRET_KEY,
    logger,
    s3_client,
    SessionLocal,
    BUCKET_VERIFY_IMAGES,
    SMS_SENDER,
    BUCKET_PROFILE_IMAGES,
    socketio_logger,
    redis_client)
import socketio
import json

sio = socketio.AsyncServer(async_mode='asgi', logger=socketio_logger)
router = APIRouter(prefix="/auth", tags=["Auth Controller"])
smsc = SMSC()


@router.post("/refresh_token", response_model=TokenResponse)
def get_refreshed_token(refresh_token: str):
    with SessionLocal() as db:
        try:
            # Декодируем refresh токен
            decoded_refresh_token = jwt.decode(refresh_token, SECRET_KEY, algorithms=["HS256"])
            if decoded_refresh_token.get("token_type") != "refresh":
                raise HTTPException(status_code=400, detail="Invalid refresh token")

            # Получаем номер телефона из токена
            phone_number = decoded_refresh_token.get("sub")
            user = db.query(User).filter_by(phone_number=phone_number).first()
            if not user:
                raise HTTPException(status_code=400, detail="User not found")

            # Генерация нового Refresh токена
            new_refresh_token_data = {"sub": phone_number, "token_type": "refresh"}
            new_refresh_token = create_refresh_token(new_refresh_token_data)

            # Обновление или добавление Refresh токена в базе данных
            refresh_token_record = db.query(RefreshToken).filter_by(user_id=user.id).first()
            if refresh_token_record:
                refresh_token_record.refresh_token = new_refresh_token
            else:
                refresh_token_record = RefreshToken(user_id=user.id, refresh_token=new_refresh_token)
                db.add(refresh_token_record)

            db.commit()

            # Генерация нового access токена
            new_token_data = {
                "sub": phone_number,  # или user.id, если требуется
                "user_id": user.id
            }
            new_access_token = create_access_token(new_token_data)
            print(new_access_token)
            return TokenResponse(access_token=f"Bearer {new_access_token}", refresh_token=new_refresh_token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Expired refresh token")
        except jwt.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/check_code", summary="Проверка кода авторизации", response_model=CheckCodeResponse,
    responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}})
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
            # Проверка корректности номера телефона
            if not validate_phone_number(phone_number):
                error_response = ErrorResponse(detail="Некорректный номер телефона", code=666)
                return JSONResponse(content=error_response.dict(), status_code=400)

            # Проверка, зарегистрирован ли номер телефона
            query = db.query(User).filter_by(phone_number=phone_number).first()
            if not query:  # Если номер не найден в базе данных
                error_response = ErrorResponse(detail="Номер телефона не зарегистрирован.", code=667)
                return JSONResponse(content=error_response.dict(), status_code=400)

            # Если номер зарегистрирован
            error_response = ErrorResponse(detail="Пользователь зарегистрирован.", code=612)
            return JSONResponse(content=error_response.dict(), status_code=400)

        except Exception as e:
            print("Error validating phone number:", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Error validating phone number")


@router.post("/send_code", summary="Отправка кода авторизации", responses={
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
    status.HTTP_200_OK: {"model": VerificationResponse}
})
def send_verification_code(phone_number: str):
    with SessionLocal() as db:
        try:
            logger.debug(f"Received request to send verification code to {phone_number}")

            if not validate_phone_number(phone_number):
                logger.warning(f"Invalid phone number: {phone_number}")
                error_response = ErrorResponse(detail="Некорректный номер телефона", code=666)
                return JSONResponse(content=error_response.dict(), status_code=400)

            if phone_number == "79000000000":
                verification_code = "834721"
                logger.debug(f"Using static verification code for phone number {phone_number}")
            else:
                verification_code = generate_verification_code()
                logger.debug(f"Generated verification code {verification_code} for phone number {phone_number}")

            temp_code = TemporaryCode(phone_number=phone_number, code=verification_code)
            db.add(temp_code)
            db.commit()
            logger.info(f"Temporary code saved to database for {phone_number}")

            if phone_number != "79000000000":
                smsc.send_sms(phone_number, f"Ваш код авторизации {verification_code}", sender=SMS_SENDER)
                logger.info(f"SMS sent to {phone_number} with code {verification_code}")

            return VerificationResponse(verification_code=verification_code)
        except Exception as e:
            logger.error(f"Error sending verification code to {phone_number}: {e}", exc_info=True)
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
            return {
                "id": user.id,
                "is_subscription": user.is_subscription,
                "gender": user.gender,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
        else:
            raise HTTPException(status_code=404, detail="Пользователь не найден")


@router.post("/upload_verify_photos")
async def upload_verify_photos(
        access_token: str = Depends(get_token),
        profile_photo: UploadFile = File(...),
        verification_selfie: UploadFile = File(...)
):
    logger.info("Received request to upload verification photos")

    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token)
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                logger.error(f"User with id {user_id} not found")
                raise HTTPException(status_code=404, detail="User not found")

            logger.info(f"User with id {user_id} found")
        except Exception as e:
            logger.error(f"Failed to retrieve user information: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve user information")

    try:
        # Логирование информации о файлах
        logger.info(
            f"Profile photo filename: {profile_photo.filename}, content type: {profile_photo.content_type}, size: {profile_photo.size}")
        logger.info(
            f"Selfie photo filename: {verification_selfie.filename}, content type: {verification_selfie.content_type}, size: {verification_selfie.size}")

        # Чтение содержимого загруженных файлов
        profile_photo_content = await profile_photo.read()
        selfie_content = await verification_selfie.read()

        # Логирование первых байтов файлов для проверки
        logger.info(f"First 100 bytes of profile photo: {profile_photo_content[:100]}")
        logger.info(f"First 100 bytes of selfie photo: {selfie_content[:100]}")

        logger.info("Both photos successfully loaded from request")

        # Сохранение файлов с оригинальными именами
        profile_photo_path = profile_photo.filename
        selfie_photo_path = verification_selfie.filename

        with open(profile_photo_path, "wb") as f:
            f.write(profile_photo_content)
        with open(selfie_photo_path, "wb") as f:
            f.write(selfie_content)

        # Исправление ориентации изображений
        profile_photo_corrected = correct_orientation(profile_photo_path)
        selfie_photo_corrected = correct_orientation(selfie_photo_path)

        # Верификация лиц с использованием исправленных изображений
        try:
            result, distance = compare_faces(profile_photo_corrected, selfie_photo_corrected)
            verification_result = "approved" if result else "denied"
            logger.info(f"Verification result: {verification_result} with distance {distance}")

            # Явное обновление записи пользователя в базе данных
            logger.info(f"Updating user verification status to: {verification_result}")
            db.query(User).filter(User.id == user_id).update({
                User.verify: verification_result
            })

            logger.info(f"Committing changes to the database for user_id: {user_id}")
            db.commit()
            logger.info(f"Changes committed successfully for user_id: {user_id}")

            try:
                # Публикация сообщения в Redis
                redis_message = {
                    "user_id": user_id,
                    "status": verification_result
                }
                json_message = json.dumps(redis_message)
                logger.info(f"JSON message: {json_message}")
                redis_client.publish("verification_updates", json_message)
                logger.info(f"Published verification update for user_id: {user_id} to Redis")

            except Exception as e:
                logger.error(f"Failed to publish verification update to Redis: {e}")

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            db.rollback()  # Откат транзакции в случае ошибки
            raise HTTPException(status_code=500, detail="Verification failed")

    except Exception as e:
        logger.error(f"Failed to process and upload photos: {e}")
        raise HTTPException(status_code=500, detail="Failed to process and upload photos")

    # Возвращаем результат верификации
    if verification_result == "approved":
        return JSONResponse(content={"status": f"Verification {verification_result}", "distance": distance},
                            status_code=200)
    else:
        return JSONResponse(content={"status": f"Verification {verification_result}", "distance": distance},
                            status_code=403)

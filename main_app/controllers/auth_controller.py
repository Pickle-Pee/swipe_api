from fastapi import HTTPException, status, APIRouter, Depends
from fastapi.responses import JSONResponse
from common.models.auth_models import TemporaryCode, RefreshToken
from common.models.user_models import User
from common.models.error_models import ErrorResponse
from common.schemas.auth_schemas import TokenResponse, CheckCodeResponse, VerificationResponse
from common.schemas.user_schemas import UserCreate, UserIdResponse
from config import SessionLocal, SECRET_KEY
from common.utils.auth_utils import create_refresh_token, create_access_token, validate_phone_number, get_token, \
    get_user_id_from_token
import jwt

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
                "user_id": user.id,
                "verify": user.verify
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


            # Создаем временный код и сохраняем его
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

            # Создание объекта UserCreate на основе переданных аргументов
            new_user_data = UserCreate(
                phone_number=user_data.phone_number,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                date_of_birth=user_data.date_of_birth,
                gender=user_data.gender,
                verify=user_data.verify,
                city_id=user_data.city_id
            )

            # Добавление данных пользователя в базу данных
            new_user = User(
                phone_number=new_user_data.phone_number,
                first_name=new_user_data.first_name,
                last_name=new_user_data.last_name,
                date_of_birth=new_user_data.date_of_birth,
                gender=new_user_data.gender,
                verify=user_data.verify,
                city_id=user_data.city_id
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
        except Exception as e:
            print("Error registering user:", e)
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
            user_id = get_user_id_from_token(access_token, SECRET_KEY)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Invalid token")

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

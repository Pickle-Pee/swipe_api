from fastapi import HTTPException, APIRouter, Depends
from fastapi.responses import JSONResponse
from config import SessionLocal, logger, SECRET_KEY
from models.user_models import User
from models.interests_models import Interest, UserInterest
from models.error_models import ErrorResponse
from schemas.interests_schemas import AddInterestsRequest, InterestResponse, UserInterestResponse
from utils.auth_utils import get_token, get_user_id_from_token

router = APIRouter(prefix="/interest", tags=["Interests Controller"])


@router.get("/user_interests", summary="Получение интересов пользователя",
            response_model=UserInterestResponse)
def read_user_interests(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Извлечение списка интересов пользователя
        user_interests = db.query(Interest).join(UserInterest).filter(UserInterest.user_id == user_id).all()

        if not user_interests:
            error_response = ErrorResponse(detail="No interests", code=622)
            return JSONResponse(content=error_response.dict(), status_code=403)

        # Формирование списка интересов для ответа
        interests_list = [{"id": interest.id, "interest_text": interest.interest_text} for interest in user_interests]

        return {"user_id": user.id, "interests": interests_list}


@router.post("/add_interests", summary="Добавление интересов пользователя")
def add_interests(request: AddInterestsRequest, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        try:
            user_id = get_user_id_from_token(access_token, SECRET_KEY)
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            # Проверка существования интересов с данными ID
            existing_interests = db.query(Interest).filter(Interest.id.in_(request.interest_ids)).all()
            if len(existing_interests) != len(request.interest_ids):
                raise HTTPException(status_code=400, detail="Один или несколько интересов не найдены")

            # Удаление текущих интересов пользователя
            db.query(UserInterest).filter(UserInterest.user_id == user_id).delete()

            # Добавление новых интересов
            for interest_id in request.interest_ids:
                new_user_interest = UserInterest(user_id=user_id, interest_id=interest_id)
                db.add(new_user_interest)

            db.commit()
            return {"message": "Интересы обновлены"}

        except Exception as e:
            print("Exception:", e)
            logger.error('Error: %s', e)
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/interests_list", summary="Получение списка доступных интересов", response_model=InterestResponse)
def get_interests_list():
    with SessionLocal() as db:
        interests = db.query(Interest).all()
        if not interests:
            raise HTTPException(status_code=404, detail="No interests found")

        interests_list = [{"id": interest.id, "interest_text": interest.interest_text} for interest in interests]

        return {"interests": interests_list}


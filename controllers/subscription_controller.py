from fastapi import HTTPException, APIRouter, Depends
from models.user_models import User
from utils.auth_utils import get_token, get_user_id_from_token
from config import SessionLocal, SECRET_KEY


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions Controller"])


@router.post("/change_subscription")
async def change_subscription(access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token, SECRET_KEY)
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_subscription = not user.is_subscription
        db.commit()

        return {"is_subscription": user.is_subscription}

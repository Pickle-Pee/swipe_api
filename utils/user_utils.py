import jwt
from fastapi import Depends, HTTPException
from config import SECRET_KEY, SessionLocal
from models.user_models import User
from utils.auth_utils import get_token


def get_current_user(token: str = Depends(get_token)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        phone_number = payload.get("sub")
        return phone_number
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def get_current_active_user(phone_number: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(User).filter_by(phone_number=phone_number).first()
    if user:
        return user
    raise HTTPException(status_code=404, detail="User not found")



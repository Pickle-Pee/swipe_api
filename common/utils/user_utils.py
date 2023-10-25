import jwt
from fastapi import Depends, HTTPException
from sqlalchemy import select
from config import SECRET_KEY, AsyncSessionLocal
from common.models import User, PushTokens
from common.utils.auth_utils import get_token


def get_current_user(token: str = Depends(get_token)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        phone_number = payload.get("sub")
        return phone_number
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


async def get_user_push_token(user_id: int):
    async with AsyncSessionLocal() as session:
        stmt = select(PushTokens).where(PushTokens.user_id == user_id)
        result = await session.execute(stmt)
        push_token = result.scalar_one_or_none()
        if push_token:
            return push_token.token
    return None

async def get_user_name(user_id: int):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user.first_name
    return None

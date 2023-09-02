from datetime import timedelta, datetime
from fastapi import Depends, APIRouter, HTTPException
from common.models.likes_models import Like, Dislike
from config import SessionLocal, SECRET_KEY
from common.utils.auth_utils import get_token, get_user_id_from_token

router = APIRouter(prefix="/likes", tags=["Likes Controller"])


@router.post("/like/{user_id}")
def like_user(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token, SECRET_KEY)

        # Проверка на взаимный лайк
        with db.begin():
            mutual_like = db.query(Like).filter(Like.user_id == user_id, Like.liked_user_id == current_user_id).first()
            if mutual_like:
                mutual_like.mutual = True
                db.commit()
                return {"message": "It's a match!"}

            existing_like = db.query(Like).filter(Like.user_id == current_user_id, Like.liked_user_id == user_id).first()
            if existing_like:
                raise HTTPException(status_code=400, detail="Already liked")

            new_like = Like(user_id=current_user_id, liked_user_id=user_id)
            db.add(new_like)
            db.commit()

        return {"message": "Liked"}


@router.post("/dislike/{user_id}")
def dislike_user(user_id: int, access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        current_user_id = get_user_id_from_token(access_token, SECRET_KEY)

        new_dislike = Dislike(
            user_id=current_user_id,
            disliked_user_id=user_id,
            timestamp=datetime.utcnow() + timedelta(days=2)
        )
        db.add(new_dislike)
        db.commit()
        return {"message": "Disliked"}

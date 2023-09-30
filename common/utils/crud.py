from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.models.auth_models import RefreshToken
from common.models.communication_models import Chat, Message
from common.models.interests_models import UserInterest
from common.models.likes_models import Dislike, Favorite, Like
from common.models.user_models import User


def delete_user_and_related_data(db: Session, user_id: int):
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.query(Dislike).filter(Dislike.user_id == user_id).delete()
    db.query(Favorite).filter(Favorite.user_id == user_id).delete()
    db.query(Like).filter(Like.user_id == user_id).delete()
    db.query(UserInterest).filter(UserInterest.user_id == user_id).delete()
    db.query(Chat).filter(Chat.user1_id == user_id).delete()
    db.query(Message).filter(
        Message.chat_id.in_(
            db.query(Chat.id).filter(or_(Chat.user1_id == user_id, Chat.user2_id == user_id))
        )
    ).delete(synchronize_session='fetch')
    db.query(Message).filter(Message.sender_id == user_id).delete()
    user = db.query(User).filter(User.id == user_id).first()

    if user:
        db.delete(user)
        db.commit()
        return True
    return False

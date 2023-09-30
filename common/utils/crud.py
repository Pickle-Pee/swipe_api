from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.models.auth_models import RefreshToken
from common.models.communication_models import Chat, Message, Media
from common.models.interests_models import UserInterest
from common.models.likes_models import Dislike, Favorite, Like
from common.models.user_models import User


def delete_user_and_related_data(db: Session, user_id: int) -> bool:
    # Удаление данных пользователя, но сохранение сообщений и чатов
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(synchronize_session=False)
    db.query(Dislike).filter(Dislike.user_id == user_id).delete(synchronize_session=False)
    db.query(Favorite).filter(Favorite.user_id == user_id).delete(synchronize_session=False)
    db.query(Like).filter(Like.user_id == user_id).delete(synchronize_session=False)
    db.query(UserInterest).filter(UserInterest.user_id == user_id).delete(synchronize_session=False)

    # Заменяем user_id на None или ID специального пользователя в чатах
    db.query(Chat).filter(Chat.user1_id == user_id).update({Chat.user1_id: None})
    db.query(Chat).filter(Chat.user2_id == user_id).update({Chat.user2_id: None})
    db.commit()

    # Удаление самого пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False


def delete_chat_and_related_messages(db: Session, chat_id: int):
    messages = db.query(Message.id).filter(Message.chat_id == chat_id).all()
    message_ids = [message[0] for message in messages]  # Изменение здесь

    if message_ids:
        db.query(Media).filter(Media.message_id.in_(message_ids)).delete(synchronize_session='fetch')
        db.query(Message).filter(Message.id.in_(message_ids)).delete(synchronize_session='fetch')

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat:
        db.delete(chat)
        db.commit()
        return True

    return False


def delete_message_and_related_media(db: Session, message_id: int):
    db.query(Media).filter(Media.message_id == message_id).delete(synchronize_session='fetch')
    message = db.query(Message).filter(Message.id == message_id).first()
    if message:
        db.delete(message)
        db.commit()
        return True

    return False

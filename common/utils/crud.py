from sqlalchemy.orm import Session

from common.models import Admin, Chat, User, Message, Media


def delete_user_and_related_data(db: Session, user_id: int) -> bool:
    # Удаление данных пользователя, но сохранение сообщений и чатов
    db.query(Chat).filter(Chat.user1_id == user_id).update({Chat.user1_id: None})
    db.query(Chat).filter(Chat.user2_id == user_id).update({Chat.user2_id: None})

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.phone_number = "000000-" + user.phone_number
        user.deleted = True
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


def get_admin_by_username(db: Session, username: str):
    return db.query(Admin).filter(Admin.username == username).first()
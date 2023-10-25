from sqlalchemy.orm import Session
from common.models import Admin, Chat, User


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


def get_admin_by_username(db: Session, username: str):
    return db.query(Admin).filter(Admin.username == username).first()
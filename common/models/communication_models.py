from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship, backref
from config import Base

MessageType = Enum('text', 'voice', 'image', name='message_type_enum')


class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True, index=True)
    user1_id = Column(Integer, ForeignKey('users.id'))
    user2_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("Message", foreign_keys="[Message.chat_id]")


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey('chats.id'))
    sender_id = Column(Integer, ForeignKey('chats.id'))
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    reply_to_message_id = Column(Integer, ForeignKey('messages.id'), nullable=True)
    replies = relationship("Message", backref=backref('reply_to', remote_side=[id]))
    message_type = Column(MessageType, default='text')
    media_url = Column(String, nullable=True)

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


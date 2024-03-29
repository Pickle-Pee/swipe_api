import enum
from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Enum, Boolean, ARRAY
from sqlalchemy.orm import relationship, backref
from config import Base


class MessageTypeEnum(enum.Enum):
    text = "text"
    voice = "voice"
    image = "image"


class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True, index=True)
    user1_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    user2_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_for_user1 = Column(Boolean, default=False)
    deleted_for_user2 = Column(Boolean, default=False)

    messages = relationship("Message", foreign_keys="[Message.chat_id]")


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey('chats.id'))
    sender_id = Column(Integer, ForeignKey('users.id'))
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    reply_to_message_id = Column(Integer, ForeignKey('messages.id'), nullable=True)
    replies = relationship("Message", backref=backref('reply_to', remote_side=[id]))
    message_type = Column(Enum(MessageTypeEnum), default=MessageTypeEnum.text)
    deleted_for_user1 = Column(Boolean, default=False)
    deleted_for_user2 = Column(Boolean, default=False)

    sender = relationship("User", back_populates="messages")
    media = relationship("Media", back_populates="message")
    voice_data = relationship("VoiceMessage", uselist=False, back_populates="message")


    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class VoiceMessage(Base):
    __tablename__ = 'voice_messages'

    message_id = Column(Integer, ForeignKey('messages.id'), primary_key=True)
    voice_data = Column(ARRAY(Integer), nullable=False)

    message = relationship("Message", back_populates="voice_data")

class Media(Base):
    __tablename__ = 'media'

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    media_url = Column(String, nullable=False)
    media_type = Column(Enum(MessageTypeEnum))
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="media")


class DateInvitations(Base):
    __tablename__ = 'date_invitations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    status = Column(Enum('pending', 'accepted', 'declined'), default='pending')
    timestamp = Column(DateTime, default=datetime.now)
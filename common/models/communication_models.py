from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, ARRAY, Enum
from sqlalchemy.orm import relationship, backref
from config import Base
from enum import Enum as PyEnum


class MessageTypeEnum(PyEnum):
    text = "text"
    voice = "voice"
    image = "image"


class InvitationStatusEnum(PyEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user1_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user2_id = Column(Integer, ForeignKey('users.id'), nullable=False)
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
    status = Column(String, default=0)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    reply_to_message_id = Column(Integer, ForeignKey('messages.id'), nullable=True)
    replies = relationship("Message", backref=backref('reply_to', remote_side=[id]))
    message_type = Column(Enum(MessageTypeEnum, name="message_type_enum"), default=MessageTypeEnum.text)
    deleted_for_user1 = Column(Boolean, default=False)
    deleted_for_user2 = Column(Boolean, default=False)

    sender = relationship("User", back_populates="messages")
    media = relationship("Media", back_populates="message")
    voice_data = relationship("VoiceMessage", uselist=False, back_populates="message")


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
    media_type = Column(Enum(MessageTypeEnum, name="message_type_enum"))
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="media")


class DateInvitations(Base):
    __tablename__ = 'date_invitations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)
    status = Column(Enum(InvitationStatusEnum, name="invitation_status_enum"), default=InvitationStatusEnum.pending)
    timestamp = Column(DateTime, default=datetime.now)

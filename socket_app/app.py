import json
import os
from datetime import datetime, timezone
import asyncio
from urllib.parse import parse_qs

# Импорт необходимых моделей и утилит
from common.models import User, Chat, Message, Media, DateInvitations, MessageTypeEnum, VoiceMessage
from common.utils import get_user_id_from_token, send_push_notification, get_user_push_token, get_user_name
from config import SessionLocal, logger, socketio_logger, add_cors, redis_client

# Импорт FastAPI и Socket.IO
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from fastapi import FastAPI, HTTPException
import socketio

from psycopg2.errors import ForeignKeyViolation


# Инициализация приложения FastAPI
fastapi_app = FastAPI()

# Добавление CORS middleware в FastAPI приложение
add_cors(fastapi_app)


@fastapi_app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": "socket_app"}

# Инициализация Socket.IO ASGI приложения
sio = socketio.AsyncServer(async_mode='asgi', logger=socketio_logger)
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

connected_users = {}

status_mapping = {
    'sending': -1,
    'sent': 0,
    'delivered': 1,
    'read': 2,
}

# Функция для проверки и приведения статуса к целому числу
def validate_message_status(status):
    if isinstance(status, str):
        try:
            status = int(status)
        except ValueError:
            raise ValueError("Invalid status value")
    elif not isinstance(status, int):
        raise TypeError("Status must be an integer")
    return status

async def _delete_related_entities(db, chat_id):
    # Удаление всех медиа, связанных с сообщениями чата
    media_items = db.query(Media).join(Message).filter(Message.chat_id == chat_id).all()
    for media in media_items:
        db.delete(media)

    # Удаление всех голосовых сообщений, связанных с сообщениями чата
    voice_messages = db.query(VoiceMessage).join(Message).filter(Message.chat_id == chat_id).all()
    for voice_message in voice_messages:
        db.delete(voice_message)

    # Удаление всех сообщений в чате
    messages = db.query(Message).filter(Message.chat_id == chat_id).all()
    for message in messages:
        db.delete(message)

    # Удаление всех приглашений на свидание, связанных с чатом
    invitations = db.query(DateInvitations).filter(DateInvitations.chat_id == chat_id).all()
    for invitation in invitations:
        db.delete(invitation)

    db.commit()



# Обработчик события запуска приложения
async def startup_event():
    asyncio.create_task(listen_for_verification_updates())

@sio.event
async def connect(sid, environ):
    query_string = environ.get('QUERY_STRING')

    # Проверка на отсутствие параметра no-auth
    if query_string and 'no-auth' in query_string:
        print('Это событие не требует аутентификации')
        return True

    # Добавляем пользователя в список подключенных, но не аутентифицированных
    connected_users[sid] = {'authenticated': False}
    socketio_logger.info(f"Client connected, SID: {sid}")

    return True

@sio.event
async def authenticate(sid, data):
    try:
        # Разбираем данные
        data_json = json.loads(data) if isinstance(data, str) else data
        access_token = data_json.get('token')

        if not access_token:
            await sio.emit('auth_response', {'status': 401, 'error': 'Отсутствует токен аутентификации'}, room=sid)
            return

        user_id = get_user_id_from_token(access_token)  # Функция проверки токена

        # Обновляем информацию о подключенном пользователе
        connected_users[sid] = {'authenticated': True, 'user_id': user_id}

        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.status = 'online'
                db.commit()

        await sio.emit('auth_response', {'status': 200}, room=sid)
        socketio_logger.info(f"User with ID {user_id} authenticated, SID: {sid}")

        # Отправляем непрочитанные сообщения
        await send_unread_messages(sid, user_id)

    except json.JSONDecodeError:
        socketio_logger.error("Failed to decode JSON")
        await sio.emit('auth_response', {'status': 400, 'error': 'Invalid JSON format'}, room=sid)
    except ExpiredSignatureError:
        socketio_logger.error("Failed to authenticate user: Token has expired")
        await sio.emit('auth_response', {'status': 401, 'error': 'Срок действия токена истек'}, room=sid)
    except InvalidTokenError:
        socketio_logger.error("Failed to authenticate user: Invalid token")
        await sio.emit('auth_response', {'status': 401, 'error': 'Недействительный токен'}, room=sid)
    except Exception as e:
        socketio_logger.error(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        await sio.emit('auth_response', {'status': 401, 'error': 'Ошибка аутентификации'}, room=sid)


@sio.event
async def send_unread_messages(sid, user_id):
    with SessionLocal() as db:
        # Получаем все чаты пользователя
        chats = db.query(Chat).filter(
            (Chat.user1_id == user_id) | (Chat.user2_id == user_id)
        ).all()

        for chat in chats:
            # Получаем непрочитанные сообщения, отправленные другому пользователем
            messages = db.query(Message).filter(
                Message.chat_id == chat.id,
                Message.sender_id != user_id,
                Message.status == 'sent'
            ).order_by(Message.id.asc()).all()

            for message in messages:
                # Обновляем статус на 'delivered' и устанавливаем delivered_at
                message.status = 'delivered'
                message.delivered_at = datetime.utcnow()
                db.add(message)
                db.commit()

                # Отправляем сообщение пользователю
                await sio.emit(
                    'new_message', {
                        'message_id': message.id,
                        'message': message.content,
                        'chat_id': message.chat_id,
                        'sender_id': message.sender_id,
                        'created_at': message.created_at.replace(tzinfo=timezone.utc).isoformat(),
                        'status': status_mapping[message.status],
                        'message_type': message.message_type.name,
                        'media_urls': [media.media_url for media in message.media],
                        'delivered_at': message.delivered_at.isoformat(),
                        'read_at': message.read_at.isoformat() if message.read_at else None,
                    }, room=sid
                )
                socketio_logger.info(f"Sent unread message ID {message.id} to user ID {user_id}")

                # Уведомляем отправителя о доставке
                sender_info = next(
                    (info for key, info in connected_users.items() if info.get('user_id') == message.sender_id), None)
                if sender_info:
                    await sio.emit(
                        'message_status_update', {
                            'message_id': message.id,
                            'status': status_mapping['delivered'],
                            'delivered_at': message.delivered_at.isoformat()
                        }, room=sender_info['sid']
                    )


@sio.event
async def get_messages(sid, data):
    # Логирование для отладки
    socketio_logger.debug(f"SID: {sid}, Connected users: {connected_users}")

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')

    # Используем sid для получения информации о пользователе
    user_info = connected_users.get(sid)

    # Проверка аутентификации
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info['user_id']

    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()

        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.id.asc()).all()

        await sio.emit(
            'get_messages',
            {
                'chatId': chat_id,
                'messages': [
                    {
                        'message_id': message.id,
                        'message': message.content,
                        'sender_id': message.sender_id,
                        'status': message.status,
                        'message_type': message.message_type.name,
                        'created_at': message.created_at.replace(tzinfo=timezone.utc).isoformat() if message.created_at else None,
                        'delivered_at': message.delivered_at.isoformat() if message.delivered_at else None,
                        'read_at': message.read_at.isoformat() if message.read_at else None,
                        'media_urls': [media.media_url for media in message.media],
                        'voice_data': message.voice_data.voice_data if message.message_type == MessageTypeEnum.voice and message.voice_data else None
                    }
                    for message in messages
                ]
            },
            room=sid
        )


@sio.event
async def send_message(sid, data):
    # Обработка входящих данных
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    # Извлечение данных из запроса
    chat_id = data.get('chat_id')
    recipient_id = data.get('recipient_id')  # Используем для логики
    message_content = data.get('message')
    external_message_id = data.get('external_message_id')
    reply_to_message_id = data.get('reply_to_message_id')
    is_admin = data.get('type') == 'admin_message'
    voice_data = data.get('voice_data')
    message_type = data.get('message_type', 'text')
    media_urls = data.get('media_urls', [])

    # Получение sender_id из информации о подключении
    sender_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not sender_info or not sender_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = sender_info.get('user_id')
    socketio_logger.info(f"User with ID {sender_id} is sending a message")

    with SessionLocal() as db:
        try:
            # Проверка существования чата
            if chat_id is None:
                if recipient_id is None:
                    await sio.emit('error', {'error': 'Recipient ID is required when chat ID is not provided'}, room=sid)
                    return

                # Проверяем, существует ли чат между sender_id и recipient_id
                chat = db.query(Chat).filter(
                    ((Chat.user1_id == sender_id) & (Chat.user2_id == recipient_id)) |
                    ((Chat.user1_id == recipient_id) & (Chat.user2_id == sender_id))
                ).first()

                if chat is None:
                    # Чат не существует, создаём новый
                    chat = Chat(
                        user1_id=sender_id,
                        user2_id=recipient_id,
                        created_at=datetime.utcnow()
                    )
                    db.add(chat)
                    db.flush()  # Получаем chat_id
                    socketio_logger.info(f"Chat created between user {sender_id} and {recipient_id} with ID {chat.id}")

                chat_id = chat.id
            else:
                # Проверяем, существует ли чат с указанным chat_id
                chat = db.query(Chat).filter(Chat.id == chat_id).first()
                if chat is None:
                    await sio.emit('error', {'error': f'Chat with ID {chat_id} not found'}, room=sid)
                    return
                # Определяем recipient_id на основе чата
                recipient_id = chat.user1_id if chat.user2_id == sender_id else chat.user2_id

            # Создание нового сообщения
            new_message = Message(
                chat_id=chat_id,
                sender_id=sender_id,
                content=message_content,
                status=status_mapping['delivered'],
                created_at=datetime.utcnow(),
                reply_to_message_id=reply_to_message_id,
                message_type=message_type
            )
            db.add(new_message)
            db.flush()  # Получение ID нового сообщения

            # Сохранение значений до коммита
            message_id = new_message.id
            created_at_str = new_message.created_at.replace(tzinfo=timezone.utc).isoformat()

            # Добавление медиа
            for url in media_urls:
                media = Media(message_id=new_message.id, media_url=url, media_type=message_type)
                db.add(media)
                socketio_logger.info(f"Media with URL {url} added to message ID {message_id}")

            if message_type == 'voice' and voice_data:
                new_voice_message = VoiceMessage(
                    message_id=new_message.id,
                    voice_data=voice_data
                )
                db.add(new_voice_message)

            # Получаем информацию о получателе из подключенных пользователей
            recipient_info = next(
                (info for key, info in connected_users.items() if info.get('user_id') == recipient_id), None
            )

            sender_name = await get_user_name(sender_id)
            title = sender_name if sender_name else "Новое сообщение"

            # Отправка сообщения получателю через сокет
            if recipient_info:
                recipient_sid = recipient_info.get('sid')
                await sio.emit(
                    'new_message', {
                        'message_id': message_id,
                        'message': message_content,
                        'chat_id': chat_id,
                        'sender_id': sender_id,
                        'reply_to_message_id': reply_to_message_id,
                        'message_type': message_type,
                        'media_urls': media_urls,
                        'created_at': created_at_str,
                        'is_admin': is_admin,
                        'status': status_mapping['delivered'],
                        'delivered_at': None,
                        'external_message_id': external_message_id,
                    }, room=recipient_sid
                )
                socketio_logger.info(f"Message ID {message_id} sent to recipient ID {recipient_id} via socket")
            else:
                socketio_logger.info(f"Recipient ID {recipient_id} not connected")
                # Отправляем push-уведомление
                recipient = db.query(User).filter(User.id == recipient_id).first()
                if recipient:
                    tokens = [token.token for token in recipient.tokens if token.active]
                    if tokens:
                        for token in tokens:
                            await send_push_notification(
                                token=token,
                                title=title,
                                body=message_content,
                                data={
                                    "chat_id": str(chat_id),
                                    "sender_id": str(sender_id),
                                    "message_id": str(message_id),
                                    "message": message_content
                                }
                            )
                    else:
                        socketio_logger.warning(f"User ID {recipient_id} has no active push tokens")
                else:
                    socketio_logger.error(f"Recipient user ID {recipient_id} not found in database")

            # Сохранение изменений в базе данных
            db.commit()
            socketio_logger.info(f"Message ID {message_id} committed to database with status {new_message.status}")

            # Отправка события завершающей обработки сообщения отправителю
            await sio.emit(
                'completer', {
                    'sender_id': sender_id,
                    'status': status_mapping['delivered'],
                    'id': message_id,
                    'external_message_id': external_message_id,
                    'chat_id': chat_id,
                    'created_at': created_at_str
                }, room=sid
            )
            socketio_logger.info(f"Completer event emitted for message ID {message_id} with status 'sent'")

        except ForeignKeyViolation as e:
            db.rollback()
            socketio_logger.error(f"ForeignKeyViolation: {e}")
            await sio.emit('error', {'error': 'Invalid chat ID'}, room=sid)
        except Exception as e:
            db.rollback()
            socketio_logger.error(f"Error in send_message handler: {e}")
            await sio.emit('error', {'error': 'Internal server error'}, room=sid)


@sio.event
async def all_messages_read(sid, data):
    socketio_logger.debug(connected_users)

    # Обработка входящих данных, если они переданы в виде строки
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')

    # Проверка наличия chat_id
    if not chat_id:
        await sio.emit('error', {'error': 'Missing required field: chat_id'}, room=sid)
        return

    # Получение информации о пользователе на основе SID
    user_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = user_info['user_id']

    with SessionLocal() as db:
        # Получение чата из базы данных
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        # Определение ID получателя
        receiver_id = chat.user1_id if chat.user1_id != sender_id else chat.user2_id

        # Обновление статуса всех сообщений в чате как "прочитано"
        messages = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.sender_id != sender_id,
            Message.status != status_mapping['read']  # Используем int значение статуса
        ).all()

        for message in messages:
            message.status = status_mapping['read']  # Исправлено: присваиваем int значение
            message.read_at = datetime.utcnow()

        db.commit()

    # Получение информации о получателе
    receiver_info = next((info for key, info in connected_users.items() if info.get('user_id') == receiver_id), None)

    # Если получатель подключён, отправляем уведомление о прочтении всех сообщений
    if receiver_info:
        receiver_sid = receiver_info.get('sid')
        if receiver_sid:
            await sio.emit(
                'all_messages_read', {
                    'chat_id': chat_id,
                    'read_at': datetime.utcnow().isoformat()
                }, room=receiver_sid
            )
            socketio_logger.info(
                f"All messages in chat ID {chat_id} marked as read by SID {sid} and notified receiver ID {receiver_id}")
        else:
            await sio.emit('error', {'error': 'Receiver SID not found'}, room=sid)
            socketio_logger.error(f"Receiver SID for receiver ID {receiver_id} not found")
    else:
        await sio.emit('error', {'error': 'Receiver not connected'}, room=sid)
        socketio_logger.error(f"Receiver ID {receiver_id} not connected")


@sio.event
async def message_delivered(sid, data):
    """
    Обработчик события 'message_delivered'.
    Ожидает данные в формате:
    {
        "message_ids": [109, 110, ...]
    }
    """
    message_ids = data.get('message_ids', [])
    socketio_logger.info(f"Received 'message_delivered' event from SID {sid} with message_ids: {message_ids}")

    if not isinstance(message_ids, list):
        await sio.emit('error', {'error': 'Invalid data format for message_ids'}, room=sid)
        return

    if not message_ids:
        await sio.emit('error', {'error': 'No message_ids provided'}, room=sid)
        return

    with SessionLocal() as db:
        for message_id in message_ids:
            message = db.query(Message).filter(Message.id == message_id).first()
            if message:
                try:
                    message.delivered_at = datetime.utcnow()
                    message.status = status_mapping['delivered']
                    db.commit()
                    socketio_logger.info(f"Message ID {message_id} marked as delivered.")

                    # Уведомление отправителя о доставке
                    sender_info = next(
                        (info for key, info in connected_users.items() if info.get('user_id') == message.sender_id), None
                    )
                    if sender_info:
                        sender_sid = sender_info.get('sid')
                        await sio.emit(
                            'message_status_update',
                            {
                                'message_id': message_id,
                                'status': status_mapping['delivered'],
                                'delivered_at': message.delivered_at.isoformat()
                            },
                            room=sender_sid
                        )
                except Exception as e:
                    db.rollback()
                    socketio_logger.error(f"Failed to update message ID {message_id}: {e}")
                    await sio.emit('error', {'error': f'Failed to update message ID {message_id}'}, room=sid)
            else:
                socketio_logger.error(f"Message with ID {message_id} not found.")
                await sio.emit(
                    'error',
                    {'error': f'Message with ID {message_id} not found.'},
                    room=sid)

@sio.event
async def message_read(sid, data):
    # Проверка, что данные переданы в виде строки, и их парсинг
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    message_ids = data.get('message_ids')

    if not isinstance(message_ids, list):
        await sio.emit('error', {'error': 'message_ids should be a list'}, room=sid)
        return

    user_info = connected_users.get(sid)
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info.get('user_id')

    # Логирование
    socketio_logger.info(f"User with ID {user_id} has read messages: {message_ids}")

    with SessionLocal() as db:
        messages = db.query(Message).filter(Message.id.in_(message_ids)).all()
        if not messages:
            await sio.emit('error', {'error': 'No messages found for provided IDs'}, room=sid)
            return

        updated_message_ids = []
        for message in messages:
            message_status = validate_message_status(message.status)
            if message_status < status_mapping['read']:
                message.status = status_mapping['read']
                message.read_at = datetime.utcnow()
                db.add(message)
                updated_message_ids.append(message.id)
                socketio_logger.info(f"Message ID {message.id} marked as read.")

        if not updated_message_ids:
            socketio_logger.info("No messages were updated.")
            return

        db.commit()

    # Отправка обновлённого статуса каждому отправителю сообщений
    for message_id in updated_message_ids:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            sender_id = message.sender_id

            # Поиск SID отправителя
            sender_sids = [
                sid for sid, info in connected_users.items()
                if info.get('user_id') == sender_id and info.get('authenticated') == True
            ]

            if sender_sids:
                socketio_logger.info(f"Attempting to send message_status_update to sender ID {sender_id} with SIDs {sender_sids}")
                for sender_sid in sender_sids:
                    await sio.emit('message_status_update', {
                        'message_id': message_id,
                        'status': status_mapping['read'],
                        'read_at': message.read_at.isoformat()
                    }, room=sender_sid)
                socketio_logger.info(f"Sent message_status_update to sender ID {sender_id} for message ID {message_id}")
            else:
                socketio_logger.warning(f"Sender ID {sender_id} not connected.")


@sio.event
async def all_messages_read(sid, data):
    socketio_logger.debug(connected_users)

    # Обработка входящих данных, если они переданы в виде строки
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')

    # Проверка наличия chat_id
    if not chat_id:
        await sio.emit('error', {'error': 'Missing required field: chat_id'}, room=sid)
        return

    # Получение информации о пользователе на основе SID
    user_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = user_info['user_id']

    with SessionLocal() as db:
        # Получение чата из базы данных
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        # Определение ID получателя
        receiver_id = chat.user1_id if chat.user1_id != sender_id else chat.user2_id

        # Обновление статуса всех сообщений в чате как "прочитано"
        messages = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.sender_id != sender_id,
            Message.status != 'read'  # Изменяем только те, которые еще не прочитаны
        ).all()

        for message in messages:
            message.status = 'read'
            message.read_at = datetime.utcnow()

        db.commit()

    # Получение информации о получателе
    receiver_info = next((info for key, info in connected_users.items() if info.get('user_id') == receiver_id), None)

    # Если получатель подключён, отправляем уведомление о прочтении всех сообщений
    if receiver_info:
        receiver_sid = receiver_info.get('sid')
        if receiver_sid:
            await sio.emit(
                'all_messages_read', {
                    'chat_id': chat_id,
                    'read_at': datetime.utcnow().isoformat()
                }, room=receiver_sid
            )
            socketio_logger.info(
                f"All messages in chat ID {chat_id} marked as read by SID {sid} and notified receiver ID {receiver_id}")
        else:
            await sio.emit('error', {'error': 'Receiver SID not found'}, room=sid)
            socketio_logger.error(f"Receiver SID for receiver ID {receiver_id} not found")
    else:
        await sio.emit('error', {'error': 'Receiver not connected'}, room=sid)
        socketio_logger.error(f"Receiver ID {receiver_id} not connected")


@sio.event
async def delete_message(sid, data):
    # Обработка входящих данных, если они переданы в виде строки
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    message_id = data.get('message_id')
    chat_id = data.get('chat_id')
    delete_for_both = data.get('delete_for_both', False)

    # Получаем информацию о пользователе на основе SID
    user_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info['user_id']
    socketio_logger.info(f"User with ID {user_id} is deleting a message in chat ID {chat_id}")

    # Проверка наличия необходимых данных
    if not message_id or not chat_id:
        await sio.emit('error', {'error': 'Invalid data'}, room=sid)
        return

    with SessionLocal() as db:
        # Получение сообщения и чата из базы данных
        message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
        chat = db.query(Chat).filter(Chat.id == chat_id).first()

        # Проверка существования сообщения и чата
        if not message or not chat:
            await sio.emit('error', {'error': 'Message or chat not found'}, room=sid)
            return

        # Проверка, является ли пользователь участником чата
        is_user1 = chat.user1_id == user_id
        is_user2 = chat.user2_id == user_id

        if not is_user1 and not is_user2:
            await sio.emit('error', {'error': 'User not found in chat'}, room=sid)
            return

        # Обновление статуса удаления сообщения
        if is_user1:
            message.deleted_for_user1 = True
        if is_user2:
            message.deleted_for_user2 = True

        # Если указано, что удаление для обоих пользователей
        if delete_for_both:
            message.deleted_for_user1 = True
            message.deleted_for_user2 = True

        db.commit()

        # Уведомление отправителю об удалении сообщения
        await sio.emit('delete_message', {'message_id': message_id, 'chat_id': chat_id}, room=sid)
        socketio_logger.info(f"Message ID {message_id} deleted in chat ID {chat_id} by user ID {user_id}")

        # Если сообщение удаляется для обоих, уведомляем получателя
        if delete_for_both:
            recipient_id = chat.user1_id if chat.user2_id == user_id else chat.user2_id
            recipient_info = next(
                (info for key, info in connected_users.items() if info.get('user_id') == recipient_id), None)

            if recipient_info:
                await sio.emit(
                    'delete_message', {'message_id': message_id, 'chat_id': chat_id},
                    room=recipient_info['sid']
                )
                socketio_logger.info(
                    f"Message ID {message_id} in chat ID {chat_id} also deleted for recipient ID {recipient_id}")


@sio.event
async def delete_chat(sid, data):
    # Обработка входящих данных, если они переданы в виде строки
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')
    delete_for_both = data.get('delete_for_both', False)

    # Получение информации о пользователе на основе SID
    user_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info.get('user_id')
    socketio_logger.info(f"User with ID {user_id} requests to delete chat with ID {chat_id}")

    # Проверка наличия chat_id
    if not chat_id:
        await sio.emit('error', {'error': 'Invalid data'}, room=sid)
        return

    with SessionLocal() as db:
        # Получение чата из базы данных
        chat = db.query(Chat).filter(Chat.id == chat_id).first()

        # Проверка существования чата
        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        # Проверка, является ли пользователь участником чата
        if chat.user1_id == user_id:
            chat.deleted_for_user1 = True
        elif chat.user2_id == user_id:
            chat.deleted_for_user2 = True
        else:
            await sio.emit('error', {'error': 'User not found in chat'}, room=sid)
            return

        # Если указано, что удаление для обоих пользователей или чат уже помечен удалённым для обоих
        if delete_for_both or (chat.deleted_for_user1 and chat.deleted_for_user2):
            # Удаление всех связанных сущностей
            await _delete_related_entities(db, chat_id)

            # Удаление самого чата
            db.delete(chat)
            db.commit()
            socketio_logger.info(f"Chat with ID {chat_id} and all related entities have been deleted.")
        else:
            # Только обновляем флаги удаления
            db.commit()

        # Уведомление отправителю об удалении чата
        await sio.emit('delete_chat', {'chat_id': chat_id}, room=sid)

        # Если удалено для обоих, уведомляем другого участника
        if delete_for_both or (chat.deleted_for_user1 and chat.deleted_for_user2):
            recipient_id = chat.user1_id if chat.user2_id == user_id else chat.user2_id
            recipient_info = next(
                (info for key, info in connected_users.items() if info.get('user_id') == recipient_id), None
            )

            if recipient_info and 'sid' in recipient_info:
                await sio.emit(
                    'delete_chat', {'chat_id': chat_id}, room=recipient_info['sid']
                )
                socketio_logger.info(f"Chat ID {chat_id} also deleted for recipient ID {recipient_id}")
            else:
                socketio_logger.warning(f"Recipient with ID {recipient_id} is not connected.")


async def listen_for_verification_updates():
    pubsub = redis_client.pubsub()
    pubsub.subscribe('verification_status')

    logger.info(f"Listening for verification updates")

    while True:
        message = pubsub.get_message()
        if message and message['type'] == 'message':
            logger.info(f"Received message from Redis: {message['data']}")
            try:
                data = message['data'].decode()
                user_id, status = data.split(':')

                # Ищем SID пользователя, если он подключен
                user_info = next((info for key, info in connected_users.items() if info.get('user_id') == int(user_id)),
                                 None)
                if user_info:
                    user_sid = next((key for key, info in connected_users.items() if info.get('user_id') == int(user_id)),
                                    None)
                    if user_sid:
                        logger.info(f"Emitting verification_update with status: {status} to sid: {user_sid}")
                        await sio.emit('verification_update', {'user_id': int(user_id), 'status': status}, room=user_sid)
            except Exception as e:
                logger.error(f"Failed to process Redis message: {e}")
        await asyncio.sleep(1)


@sio.event
async def send_date_invitation(sid, data):
    # Проверка данных и парсинг JSON, если необходимо
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')

    # Проверка наличия chat_id
    if not chat_id:
        await sio.emit('error', {'error': 'Missing chat ID'}, room=sid)
        return

    # Получаем информацию о пользователе на основе SID
    user_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = user_info['user_id']
    socketio_logger.info(f"User with ID {sender_id} is sending a date invitation to chat ID {chat_id}")

    with SessionLocal() as db:
        # Получение чата из базы данных
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is None:
            await sio.emit('error', {'error': f'Chat with ID {chat_id} not found'}, room=sid)
            return

        # Определение ID получателя
        recipient_id = chat.user1_id if chat.user2_id == sender_id else chat.user2_id

        # Записываем приглашение в базу данных
        new_invitation = DateInvitations(
            sender_id=sender_id,
            recipient_id=recipient_id,
            chat_id=chat_id,
            status='pending'
        )
        db.add(new_invitation)
        db.commit()
        socketio_logger.info(f"Date invitation from user ID {sender_id} to user ID {recipient_id} recorded in database")

        # Получение имени отправителя
        sender = db.query(User).filter(User.id == sender_id).first()
        sender_name = sender.first_name if sender else "Неизвестный пользователь"

        # Отправляем уведомление адресату, если он онлайн
        recipient_info = next((info for key, info in connected_users.items() if info.get('user_id') == recipient_id),
                              None)
        if recipient_info:
            recipient_sid = recipient_info.get('sid')
            await sio.emit(
                'date_invitation', {
                    'chat_id': chat_id,
                    'sender_id': sender_id,
                    'action': 'invitation_sent',
                    'status': 'pending'
                }, room=recipient_sid
            )

        # Отправляем пуш-уведомление
        push_token = await get_user_push_token(recipient_id)
        if push_token:
            title = "Новое приглашение на свидание"
            message_content = f"{sender_name} приглашает вас на свидание"
            await send_push_notification(
                push_token,
                title,
                message_content,
                data={
                    'invitation_type': 'date'
                },
                aps={
                    "content-available": 1
                }
            )
            socketio_logger.info(f"Push notification sent to recipient ID {recipient_id} with token {push_token}")

        # Отправляем подтверждение отправителю
        await sio.emit(
            'date_invitation', {
                'sender_id': sender_id,
                'status': 'pending',
                'chat_id': chat_id,
                'action': 'invitation_sent'
            }, room=sid
        )
        socketio_logger.info(f"Date invitation sent to recipient ID {recipient_id} via socket")


@sio.event
async def respond_date_invitation(sid, data):
    # Проверка данных и парсинг JSON, если необходимо
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')
    response = data.get('response')  # принять или отклонить

    # Проверка наличия chat_id и response
    if not chat_id or response not in ['accepted', 'declined']:
        await sio.emit('error', {'error': 'Missing or invalid data'}, room=sid)
        return

    # Получаем информацию о пользователе на основе SID
    user_info = connected_users.get(sid)

    # Проверка аутентификации пользователя
    if not user_info or not user_info.get('authenticated'):
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = user_info['user_id']
    socketio_logger.info(
        f"User with ID {sender_id} responded to date invitation in chat ID {chat_id} with response: {response}")

    with SessionLocal() as db:
        # Получаем имя отправителя из базы данных
        sender = db.query(User).filter(User.id == sender_id).first()
        sender_name = sender.name if sender else "Неизвестный пользователь"

        # Получение чата из базы данных
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is None:
            await sio.emit('error', {'error': f'Chat with ID {chat_id} not found'}, room=sid)
            return

        # Обновляем статус приглашения в базе данных
        invitation = db.query(DateInvitations).filter(
            DateInvitations.chat_id == chat_id, DateInvitations.recipient_id == sender_id).first()
        if invitation:
            invitation.status = response
            db.commit()
            socketio_logger.info(f"Date invitation status updated to {response} in database")

        recipient_id = chat.user1_id if chat.user2_id == sender_id else chat.user2_id
        recipient_info = next((info for key, info in connected_users.items() if info.get('user_id') == recipient_id),
                              None)

        # Отправляем ответ инициатору приглашения
        if recipient_info:
            recipient_sid = recipient_info.get('sid')
            await sio.emit(
                'date_invitation_response', {
                    'chat_id': chat_id,
                    'sender_id': sender_id,
                    'response': response
                }, room=recipient_sid
            )

            # Отправляем пуш-уведомление инициатору приглашения
            push_token = await get_user_push_token(recipient_id)
            if push_token:
                title = "Ответ на ваше приглашение"
                if response == "accepted":
                    message_content = f"{sender_name} принял ваше приглашение на свидание"
                else:
                    message_content = f"Пользователь {sender_name} отклонил ваше приглашение на свидание"
                await send_push_notification(
                    push_token,
                    title,
                    message_content,
                    data={
                        'response_type': 'date'
                    },
                    aps={
                        "content-available": 1
                    }
                )
                socketio_logger.info(f"Push notification sent to initiator ID {recipient_id} with token {push_token}")
            socketio_logger.info(f"Date response {response} sent to initiator ID {recipient_id} via socket")

async def send_scheduled_notification():
    notification_data = {
        "title": "Напоминание",
        "body": "Пора проверить приложение!"
    }
    for sid in list(connected_users.keys()):
        await sio.emit('scheduled_notification', notification_data, room=sid)
    socketio_logger.info("Запланированное уведомление отправлено.")


@fastapi_app.get("/test_push")
async def test_push():
    await send_scheduled_notification()
    return {"message": "Тест пуш отправлен"}


@sio.event
async def disconnect(sid):
    print(f"Client with SID {sid} disconnected")
    user_info = connected_users.pop(sid, None)
    if user_info and user_info.get('authenticated'):
        user_id = user_info.get('user_id')
        # Обновляем статус пользователя в базе данных
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.status = 'offline'
                db.commit()
        socketio_logger.info(f"User with ID {user_id} marked as offline in the database")


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1025)

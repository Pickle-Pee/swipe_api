import json
import os

import httpx
import socketio
from datetime import datetime
from common.utils.auth_utils import get_user_id_from_token
from common.utils.service_utils import send_push_notification
from common.utils.user_utils import get_user_push_token, get_user_name
from config import SessionLocal, logger, engine, socketio_logger, sio, socket_app
from urllib.parse import parse_qs

from common.models.auth_models import *
from common.models.user_models import *
from common.models.interests_models import *
from common.models.cities_models import *
from common.models.likes_models import *
from common.models.communication_models import *
from common.models.error_models import *

connected_users = {}


async def startup_event():
    # Создание всех таблиц в базе данных при старте приложения
    Base.metadata.create_all(bind=engine)


@sio.event
async def connect(sid, environ):
    query_string = environ.get('QUERY_STRING')
    parsed_params = parse_qs(query_string)
    access_token = parsed_params.get('token', [None])[0]

    if 'no-auth' in environ.get('QUERY_STRING', ''):
        print('This event does not require authentication')
        return True

    if not access_token:
        return False

    try:
        user_id = get_user_id_from_token(access_token)
    except Exception as e:
        socketio_logger.error(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        return False

    connected_users[user_id] = {'sid': sid, 'user_id': user_id}

    socketio_logger.info(f"User with ID {user_id} connected, SID: {sid}")

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.status = 'online'
            db.commit()

status_mapping = {
    'delivered': 1,
    'read': 2,
}


@sio.event
async def get_messages(sid, data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')
    user_info = next((info for info in connected_users.values() if info['sid'] == sid), None)

    if not user_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info.get('user_id')
    socketio_logger.info(f"User with ID {user_id} requested messages for chat ID {chat_id}")

    if user_id in connected_users:
        connected_users[user_id]['sid'] = sid
    else:
        connected_users[user_id] = {'sid': sid, 'user_id': user_id}

    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()

        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        is_user1 = chat.user1_id == user_id

        messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.id.asc()).all()
        filtered_messages = []

        for message in messages:
            socketio_logger.info(
                f"Message ID {message.id}: deleted_for_user1={message.deleted_for_user1}, "
                f"deleted_for_user2={message.deleted_for_user2}, is_user1={is_user1}, user_id={user_id}"
            )

            # Проверяем, удалено ли сообщение для текущего пользователя
            if (is_user1 and message.deleted_for_user1) or (not is_user1 and message.deleted_for_user2):
                socketio_logger.info(f"Message ID {message.id} filtered for user ID {user_id}")
                continue  # Пропускаем это сообщение, если оно было удалено

            message_dict = {
                'message_id': message.id,
                'message': message.content,
                'sender_id': message.sender_id,
                'status': status_mapping.get(message.status, -1),
                'message_type': message.message_type.name,
                'media_urls': [media.media_url for media in message.media]
            }

            filtered_messages.append(message_dict)

        socketio_logger.info(f"Data to be emitted: {json.dumps({'messages': filtered_messages}, default=str)}")

        await sio.emit('get_messages', {'chatId': chat_id, 'messages': filtered_messages}, room=sid)


@sio.event
async def send_message(sid, data):
    if isinstance(data, str):
        data = json.loads(data)

    chat_id = data.get('chat_id')
    message_content = data.get('message')
    external_message_id = data.get('external_message_id')
    reply_to_message_id = data.get('reply_to_message_id')

    # Получаем sender_id из информации о подключении
    sender_info = next((info for info in connected_users.values() if info['sid'] == sid), None)

    if not sender_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = sender_info.get('user_id')
    socketio_logger.info(f"User with ID {sender_id} is sending a message to chat ID {chat_id}")  # Логирование отправки сообщения

    message_type = data.get('message_type', 'text')
    media_urls = data.get('media_urls', [])

    with SessionLocal() as db:
        new_message = Message(
            chat_id=chat_id,
            sender_id=sender_id,
            content=message_content,
            status='delivered',
            delivered_at=datetime.now(),
            reply_to_message_id=reply_to_message_id,
            message_type=message_type
        )
        db.add(new_message)
        db.flush()

        message_id = new_message.id

        # Логирование добавления медиа
        for url in media_urls:
            media = Media(message_id=new_message.id, media_url=url, media_type=message_type)
            db.add(media)
            socketio_logger.info(f"Media with URL {url} added to message ID {message_id}")

        db.commit()
        socketio_logger.info(f"Message ID {message_id} committed to database")

        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is None:
            await sio.emit('error', {'error': f'Chat with ID {chat_id} not found'}, room=sid)
            return

        recipient_id = chat.user1_id if chat.user2_id == sender_id else chat.user2_id
        recipient_info = connected_users.get(recipient_id)

        sender_name = await get_user_name(sender_id)
        title = sender_name if sender_name else "Новое сообщение"

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
                    'media_urls': media_urls
                }, room=recipient_sid
            )
            socketio_logger.info(f"Message ID {message_id} sent to recipient ID {recipient_id} via socket")

        push_token = await get_user_push_token(recipient_id)
        if push_token:
            if message_content is None:
                logger.error("message_content is None, cannot send push notification.")
            else:
                await send_push_notification(
                    push_token,
                    title,
                    message_content,
                    data={
                        'message_type': message_type
                    },
                    aps={
                        "content-available": 1
                    })
                socketio_logger.info(f"Push notification sent to recipient ID {recipient_id} with token {push_token}")

    await sio.emit(
        'completer', {
            'sender_id': sender_id,
            'status': 1,
            'id': message_id,
            'external_message_id': external_message_id,
            'chat_id': chat_id
        }, room=sid
    )
    socketio_logger.info(f"Completer event emitted for message ID {message_id}")




@sio.event
async def message_delivered(sid, data):
    message_id = data.get('message_id')
    with SessionLocal() as db:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.status = 'delivered'
            message.delivered_at = datetime.now()
            db.commit()
    await sio.emit('message_status', {'message_id': message_id, 'status': 'delivered'}, room=sid)


@sio.event
async def message_read(sid, data):
    message_id = data.get('message_id')
    with SessionLocal() as db:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.status = 'read'
            message.read_at = datetime.now()
            db.commit()
    await sio.emit('message_status', {'message_id': message_id, 'status': 'read'}, room=sid)


@sio.event
async def all_messages_read(sid, data):
    socketio_logger.debug(connected_users)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')

    if not chat_id:
        await sio.emit('error', {'error': 'Missing required fields'}, room=sid)
        return

    sender_id = None
    for user_info in connected_users.values():
        if user_info['sid'] == sid:
            sender_id = user_info['user_id']
            break

    if sender_id is None:
        await sio.emit('error', {'error': 'Sender not found'}, room=sid)
        return

    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        receiver_id = chat.user1_id if chat.user1_id != sender_id else chat.user2_id

    if not chat_id:
        await sio.emit('error', {'error': 'Missing required field: chat_id'}, room=sid)
        return

    with SessionLocal() as db:
        messages = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.sender_id != sender_id
        ).all()

        for message in messages:
            message.status = 'read'
            message.read_at = datetime.now()

        db.commit()

    receiver_info = connected_users.get(receiver_id)
    if receiver_info:
        receiver_sid = receiver_info.get('sid')
        if receiver_sid:
            await sio.emit(
                'all_messages_read', {
                    'chat_id': chat_id
                }, room=receiver_sid
            )
        else:
            await sio.emit('error', {'error': 'Receiver SID not found'}, room=sid)
    else:
        await sio.emit('error', {'error': 'Receiver not connected'}, room=sid)


@sio.event
async def delete_message(sid, data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    message_id = data.get('message_id')
    chat_id = data.get('chat_id')
    delete_for_both = data.get('delete_for_both', False)

    # Получаем user_id таким же образом, как и в get_messages
    user_info = next((info for info in connected_users.values() if info['sid'] == sid), None)

    if not user_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    user_id = user_info.get('user_id')
    socketio_logger.info(f"User with ID {user_id} is deleting a message in chat ID {chat_id}")

    if not message_id or not chat_id:
        await sio.emit('error', {'error': 'Invalid data'}, room=sid)
        return

    with SessionLocal() as db:
        message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
        chat = db.query(Chat).filter(Chat.id == chat_id).first()

        if not message or not chat:
            await sio.emit('error', {'error': 'Message or chat not found'}, room=sid)
            return

        is_user1 = chat.user1_id == user_id
        is_user2 = chat.user2_id == user_id

        if not is_user1 and not is_user2:
            await sio.emit('error', {'error': 'User not found in chat'}, room=sid)
            return

        if is_user1:
            message.deleted_for_user1 = True
        elif is_user2:
            message.deleted_for_user2 = True

        if delete_for_both:
            message.deleted_for_user1 = True
            message.deleted_for_user2 = True

        db.commit()

        # Включаем chat_id в ответ
        await sio.emit('delete_message', {'message_id': message_id, 'chat_id': chat_id}, room=sid)

        if delete_for_both:
            chat = db.query(Chat).filter(Chat.id == chat_id).first()
            recipient_id = chat.user1_id if chat.user2_id == user_id else chat.user2_id
            recipient_info = connected_users.get(recipient_id)

            if recipient_info:
                await sio.emit(
                    'delete_message', {'message_id': message_id, 'chat_id': chat_id},  # Включаем chat_id в ответ
                    room=recipient_info['sid'])


@sio.event
async def delete_chat(sid, data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            await sio.emit('error', {'error': 'Invalid data format'}, room=sid)
            return

    chat_id = data.get('chat_id')
    delete_for_both = data.get('delete_for_both', False)

    # Получаем user_id таким же образом, как и в get_messages
    socketio_logger.info(f"Connected users: {connected_users}")  # Заменено на logger
    user_info = next((info for info in connected_users.values() if info['sid'] == sid), None)

    if not user_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    socketio_logger.info(f"User info for sid {sid}: {user_info}")  # Заменено на logger
    user_id = user_info.get('user_id')

    if not chat_id:
        await sio.emit('error', {'error': 'Invalid data'}, room=sid)
        return

    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()

        if not chat:
            await sio.emit('error', {'error': 'Chat not found'}, room=sid)
            return

        if chat.user1_id == user_id:
            chat.deleted_for_user1 = True
        elif chat.user2_id == user_id:
            chat.deleted_for_user2 = True
        else:
            await sio.emit('error', {'error': 'User not found in chat'}, room=sid)
            return

        if delete_for_both:
            chat.deleted_for_user1 = True
            chat.deleted_for_user2 = True

        db.commit()

        socketio_logger.info(f"User with ID {user_id} deleted chat with ID {chat_id}")  # Добавлено логирование

        await sio.emit('delete_chat', {'chat_id': chat_id}, room=sid)

        if delete_for_both or (chat.deleted_for_user1 and chat.deleted_for_user2):
            recipient_id = chat.user1_id if chat.user2_id == user_id else chat.user2_id
            recipient_info = connected_users.get(recipient_id)

            if recipient_info:
                await sio.emit(
                    'delete_chat', {'chat_id': chat_id}, room=recipient_info['sid'])


@sio.event
async def update_verification_status(sid, data):
    logger.info(f"Received event data: {data}")


    if isinstance(data, str):
        data = json.loads(data)

    user_id = data.get('user_id')
    status = data.get('status')

    user_sid = connected_users.get(user_id)

    if user_sid:
        await sio.emit('verification_update', {'status': status}, room=user_sid)
    else:
        print(f"User with ID {user_id} is not connected.")

    if not user_id or not status:
        logger.error("Missing data")
        await sio.emit('error', {'error': 'Missing data'}, room=sid)
        return

    user_info = next((info for info in connected_users.values() if info['user_id'] == user_id), None)

    if not user_info:
        logger.error("User not found")
        await sio.emit('error', {'error': 'User not found'}, room=sid)
        return

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error("User not found in DB")
            await sio.emit('error', {'error': 'User not found in DB'}, room=sid)
            return

        user.is_verified = status == 'approved'
        db.commit()

        logger.info(f"Emitting verification_update with status: {status} to sid: {user_info['sid']}")
        await sio.emit('verification_update', {'status': status}, room=user_info['sid'])


@sio.event
async def send_date_invitation(sid, data):
    # Проверка данных
    if isinstance(data, str):
        data = json.loads(data)
    chat_id = data.get('chat_id')

    # Получаем sender_id из информации о подключении
    sender_info = next((info for info in connected_users.values() if info['sid'] == sid), None)
    if not sender_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = sender_info.get('user_id')
    socketio_logger.info(f"User with ID {sender_id} is sending a date invitation to chat ID {chat_id}")

    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is None:
            await sio.emit('error', {'error': f'Chat with ID {chat_id} not found'}, room=sid)
            return

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

        recipient_info = connected_users.get(recipient_id)

        # Отправляем уведомление адресату
        if recipient_info:
            recipient_sid = recipient_info.get('sid')
            await sio.emit(
                'date_invitation', {
                    'chat_id': chat_id,
                    'sender_id': sender_id,
                }, room=recipient_sid
            )

            socketio_logger.info(
                f"Preparing to send completer for date invitation from user ID {sender_id} to chat ID {chat_id}")

            await sio.emit(
                'completer', {
                    'sender_id': sender_id,
                    'status': 1,
                    'chat_id': chat_id,
                    'action': 'invitation_sent'
                }, room=sid
            )
            socketio_logger.info(f"Date invitation sent to recipient ID {recipient_id} via socket")



@sio.event
async def respond_date_invitation(sid, data):
    if isinstance(data, str):
        data = json.loads(data)
    chat_id = data.get('chat_id')
    response = data.get('response')  # принять или отклонить

    # Получаем sender_id из информации о подключении
    sender_info = next((info for info in connected_users.values() if info['sid'] == sid), None)
    if not sender_info:
        await sio.emit('error', {'error': 'Authentication failed'}, room=sid)
        return

    sender_id = sender_info.get('user_id')
    socketio_logger.info(f"User with ID {sender_id} responded to date invitation in chat ID {chat_id} with response: {response}")

    with SessionLocal() as db:
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
        recipient_info = connected_users.get(recipient_id)

        # Отправляем ответ инициатору приглашения
        if recipient_info:
            recipient_sid = recipient_info.get('sid')
            await sio.emit(
                'date_response', {
                    'chat_id': chat_id,
                    'sender_id': sender_id,
                    'response': response
                }, room=recipient_sid
            )
            await sio.emit(
                'completer', {
                    'sender_id': sender_id,
                    'status': 1,
                    'chat_id': chat_id,
                    'action': 'invitation_response',
                    'response': response
                }, room=sid
            )
            socketio_logger.info(f"Date response {response} sent to initiator ID {recipient_id} via socket")



@sio.event
async def disconnect(sid):
    user_id = next((user_id for user_id, info in connected_users.items() if info['sid'] == sid), None)

    if user_id:
        del connected_users[user_id]
        print(f"Removed user {user_id} with sid {sid} from connected_users")

        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.status = 'offline'
                db.commit()


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1025)

import json
import os
import socketio
from datetime import datetime
from common.models.communication_models import Chat, Message
from common.utils.auth_utils import get_user_id_from_token
from config import SessionLocal, SECRET_KEY, logger
from urllib.parse import parse_qs

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*", logger=True, engineio_logger=True)
socket_app = socketio.ASGIApp(sio)

connected_users = {}


@sio.event
async def connect(sid, environ):
    query_string = environ.get('QUERY_STRING')
    parsed_params = parse_qs(query_string)
    access_token = parsed_params.get('token', [None])[0]

    if not access_token:
        return False

    try:
        user_id = get_user_id_from_token(access_token)
    except Exception as e:
        print(f"Failed to authenticate user. Exception: {type(e).__name__}, Message: {str(e)}")
        return False

    connected_users[user_id] = {'sid': sid, 'user_id': user_id}


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

    if user_id in connected_users:
        connected_users[user_id]['sid'] = sid
    else:
        connected_users[user_id] = {'sid': sid, 'user_id': user_id}

    with SessionLocal() as db:
        messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.id.asc()).all()
        filtered_messages = []

        for message in messages:
            message_dict = {
                'content': message.content,
                'sender_id': message.sender_id,
                'status': status_mapping.get(message.status, -1)
            }
            filtered_messages.append(message_dict)

        logger.info(f"Data to be emitted: {json.dumps({'messages': filtered_messages}, default=str)}")

        await sio.emit('get_messages', {'chatId': chat_id, 'messages': filtered_messages}, room=sid)


@sio.event
async def send_message(sid, data):
    if isinstance(data, str):
        data = json.loads(data)

    sender_id = data.get('sender_id')
    chat_id = data.get('chat_id')
    message_content = data.get('message')
    external_message_id = data.get('external_message_id')
    sender_info = connected_users.get(sender_id)
    reply_to_message_id = data.get('reply_to_message_id')

    # Получение типа сообщения и URL медиа
    message_type = data.get('message_type', 'text')  # По умолчанию используется текстовое сообщение
    media_url = data.get('media_url')  # URL медиафайла, если он есть

    if not sender_info:
        await sio.emit('completer', {'sender_id': sender_id, 'status': 1, 'id': None})
        return

    with SessionLocal() as db:
        new_message = Message(
            chat_id=chat_id,
            sender_id=sender_id,
            content=message_content,
            status='delivered',
            delivered_at=datetime.now(),
            reply_to_message_id=reply_to_message_id,
            message_type=message_type,
            media_url=media_url
        )
        db.add(new_message)
        db.commit()
        message_id = new_message.id

        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is None:
            await sio.emit('error', {'error': f'Chat with ID {chat_id} not found'}, room=sid)
            return

        recipient_id = chat.user1_id if chat.user2_id == sender_id else chat.user2_id

        recipient_info = connected_users.get(recipient_id)
        if recipient_info:
            recipient_sid = recipient_info.get('sid')
            await sio.emit(
                'new_message', {
                    'message_id': message_id,
                    'message_content': message_content,
                    'chat_id': chat_id,
                    'sender_id': sender_id,
                    'reply_to_message_id': reply_to_message_id,
                    'message_type': message_type,
                    'media_url': media_url
                }, room=recipient_sid
            )

    await sio.emit(
        'completer', {
            'sender_id': sender_id,
            'status': 1,
            'id': message_id,
            'external_message_id': external_message_id,
            'chat_id': chat_id
        }, room=sid
    )


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
    logger.debug(connected_users)
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
async def disconnect(sid):
    user_id = next((user_id for user_id, info in connected_users.items() if info['sid'] == sid), None)

    if user_id:
        del connected_users[user_id]
        print(f"Removed user {user_id} with sid {sid} from connected_users")


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1025)

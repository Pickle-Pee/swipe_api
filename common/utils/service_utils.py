import json

import requests
from fastapi.security import HTTPBearer
from socketio import AsyncClient

from .user_utils import deactivate_push_token
from config import IS_DEMO, PUSH_URL, logger
from PIL import Image
import io

security = HTTPBearer()
sio_client = AsyncClient()


async def send_push_notification(token: str, title: str, body: str, data: dict, **_options):
    if IS_DEMO:
        logger.info("Push notification skipped in demo mode")
        return None
    push_message = {
        "title": title,
        "body": body,
        "data": data,
        "token": token
    }
    try:
        response = requests.post(
            PUSH_URL,
            json=push_message
        )
        if response.status_code != 200:
            error_detail = response.json().get('detail', {})
            error_message = error_detail.get('error', '')
            if 'not registered' in error_message or 'invalid' in error_message:
                # Деактивируем токен в базе данных
                deactivate_push_token(token)
            logger.error(
                "Push notification failed http_status=%s", response.status_code
            )
    except Exception:
        logger.exception("Push notification transport failed")


async def send_event_to_socketio(url, event_name, event_data):
    try:
        headers = {'no-auth': 'true'}
        await sio_client.connect(url, headers=headers)
        await sio_client.emit(event_name, event_data)
        await sio_client.disconnect()
    except Exception as e:
        logger.error(f"Error sending event to Socket.IO server: {e}")


def convert_to_jpeg(image_file):
    """Конвертирует изображение в формат JPEG."""
    image = Image.open(image_file)
    jpeg_image_io = io.BytesIO()
    image = image.convert("RGB")
    image.save(jpeg_image_io, format="JPEG")
    jpeg_image_io.seek(0)
    return jpeg_image_io

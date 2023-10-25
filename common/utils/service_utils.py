import json
from fastapi.security import HTTPBearer
from socketio import AsyncClient
from config import logger
import httpx

security = HTTPBearer()
sio_client = AsyncClient()

async def send_push_notification(token, title, body, data, aps):
    url = "http://push_app:1026/send_push"
    payload = {
        "token": token,
        "title": title,
        "body": body,
        "data": data,
        "aps": aps
    }

    logger.info(f"Sending push notification: {json.dumps(payload, indent=2)}")

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)

        logger.info(f"Received response: {response.status_code} - {response.text}")

        if response.status_code != 200:
            logger.error(f"Failed to send push notification: {response.status_code}")
            return None

        return response.json()


async def send_event_to_socketio(url, event_name, event_data):
    try:
        headers = {'no-auth': 'true'}
        await sio_client.connect(url, headers=headers)
        await sio_client.emit(event_name, event_data)
        await sio_client.disconnect()
    except Exception as e:
        logger.error(f"Error sending event to Socket.IO server: {e}")
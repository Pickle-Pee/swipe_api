import json

from fastapi import HTTPException
from config import DADATA_API_URL, DADATA_API_TOKEN, logger
import httpx


async def get_cities(query: str):
    headers = {
        "Authorization": f"Token {DADATA_API_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {"query": query, "locations": [{"country": "Россия"}], "from_bound": {"value": "city"}}

    async with httpx.AsyncClient() as client:
        response = await client.post(DADATA_API_URL, json=data, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to retrieve data")

    cities = [suggestion["value"] for suggestion in response.json()["suggestions"] if suggestion["data"]["city"]]
    return cities


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
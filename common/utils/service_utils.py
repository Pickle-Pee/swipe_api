from fastapi import HTTPException
from config import DADATA_API_URL, DADATA_API_TOKEN, DADATA_API_SECRET
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

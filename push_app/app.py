from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import firebase_admin
from firebase_admin import messaging, credentials
from config import FIREBASE_CREDENTIALS_PATH
import os


app = FastAPI()

cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)


class PushMessage(BaseModel):
    token: str
    title: str
    body: str


@app.post("/send_push")
async def send_push(msg: PushMessage):
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=msg.title,
                body=msg.body),
            token=msg.token)

        response = messaging.send(message)
        return {"success": True, "response": response}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": str(e)})


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(app, host=app_host, port=1026)


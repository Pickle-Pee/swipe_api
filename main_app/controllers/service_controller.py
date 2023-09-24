import os
import time

from fastapi import UploadFile, File, APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from common.models.user_models import User
from config import s3_client, BUCKET_MESSAGE_IMAGES, BUCKET_MESSAGE_VOICES, BUCKET_PROFILE_IMAGES, SessionLocal
from common.utils.auth_utils import get_user_id_from_token, get_token

router = APIRouter(prefix="/service", tags=["Auth Controller"])


@router.post("/upload/message-image/{chat_id}/{message_id}/")
async def upload_message_image(
        chat_id: int,
        message_id: int,
        file: UploadFile = File(...),
        access_token: str = Depends(get_token)):

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        db.commit()

    extension = file.filename.split(".")[-1]
    file_name = f"message_{chat_id}_{message_id}.{extension}"
    with open(file_name, "wb") as buffer:
        buffer.write(file.file.read())

    with open(file_name, "rb") as f:
        s3_client.upload_fileobj(f, BUCKET_MESSAGE_IMAGES, file_name)

    os.remove(file_name)
    return {"file_key": file_name}


@router.post("/upload/message_voice/{chat_id}/{message_id}/")
async def upload_message_voice(
        chat_id: int,
        message_id: int,
        file: UploadFile = File(...),
        access_token: str = Depends(get_token)):

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        db.commit()

    extension = file.filename.split(".")[-1]
    file_name = f"message_{chat_id}_{message_id}.{extension}"
    with open(file_name, "wb") as buffer:
        buffer.write(file.file.read())

    with open(file_name, "rb") as f:
        s3_client.upload_fileobj(f, BUCKET_MESSAGE_VOICES, file_name)

    os.remove(file_name)
    return {"file_key": file_name}


@router.post("/upload")
async def upload_profile_image(
        file: UploadFile = File(...),
        access_token: str = Depends(get_token)):
    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        db.commit()

    image_id = str(int(time.time()))

    extension = file.filename.split(".")[-1]
    file_name = f"profile_{user_id}_{image_id}.{extension}"
    with open(file_name, "wb") as buffer:
        buffer.write(file.file.read())

    with open(file_name, "rb") as f:
        s3_client.upload_fileobj(f, BUCKET_PROFILE_IMAGES, file_name)

    os.remove(file_name)
    return {"file_key": file_name}


@router.get("/get_file/{file_key}")
async def get_file(file_key: str):
    file_obj = s3_client.get_object(Bucket=BUCKET_MESSAGE_IMAGES, Key=file_key)
    return StreamingResponse(file_obj['Body'],
                             media_type="application/octet-stream",
                             headers={"Content-Disposition": f"attachment; filename={file_key}"})

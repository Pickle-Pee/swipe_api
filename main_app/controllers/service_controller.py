import os
import time
import magic
from datetime import datetime
from typing import Optional

from fastapi import UploadFile, File, APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from common.models.user_models import User
from config import s3_client, BUCKET_MESSAGE_IMAGES, BUCKET_MESSAGE_VOICES, BUCKET_PROFILE_IMAGES, SessionLocal, logger
from common.utils.auth_utils import get_user_id_from_token, get_token

router = APIRouter(prefix="/service", tags=["Auth Controller"])


@router.post("/upload/message_image/{chat_id}")
async def upload_message_image(
        chat_id: int,
        file: UploadFile = File(...),
        access_token: str = Depends(get_token),
        tag: Optional[str] = None):
    logger.info(f"Received request to upload image for chat_id {chat_id}")

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"User with id {user_id} not found")
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        logger.info(f"User with id {user_id} found")
        db.commit()

    mime = magic.Magic(mime=True)
    mime_type = mime.from_buffer(file.file.read(1024))
    file.file.seek(0)  # reset the file cursor to the beginning

    # Map MIME types to file extensions
    mime_to_ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
    }

    extension = mime_to_ext.get(mime_type)
    if extension is None:
        logger.error(f"Unsupported file type {mime_type}")
        raise HTTPException(status_code=400, detail="Unsupported file type")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = f"image_{chat_id}_{timestamp}.{extension}"

    logger.info(f"Uploading file {file_name}")

    try:
        # Always write the file to the buffer before uploading to S3
        with open(file_name, "wb") as buffer:
            buffer.write(file.file.read())

        # Upload the file to S3
        with open(file_name, "rb") as f:
            s3_client.upload_fileobj(f, BUCKET_MESSAGE_IMAGES, file_name)

        logger.info(f"File {file_name} uploaded successfully to S3")
    except Exception as e:
        logger.error(f"Failed to upload file {file_name} to S3: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")
    finally:
        # Clean up the local file whether the upload was successful or not
        if os.path.exists(file_name):
            os.remove(file_name)
            logger.info(f"Local file {file_name} removed")

    return {"file_key": file_name}


@router.post("/upload/message_voice/{chat_id}")
async def upload_message_voice(
        chat_id: int,
        file: UploadFile = File(...),
        access_token: str = Depends(get_token)):
    logger.info(f"Received request to upload voice message for chat_id {chat_id}")

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"User with id {user_id} not found")
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        logger.info(f"User with id {user_id} found")
        db.commit()

    # Ensure the filename is safe
    file_name = "".join([c for c in file.filename if c.isalnum() or c in ('.', '_')])
    if not file_name:
        logger.error(f"Invalid file name {file.filename}")
        raise HTTPException(status_code=400, detail="Invalid file name")

    logger.info(f"Uploading file {file_name}")

    try:
        # Always write the file to the buffer before uploading to S3
        with open(file_name, "wb") as buffer:
            buffer.write(file.file.read())

        # Upload the file to S3
        with open(file_name, "rb") as f:
            s3_client.upload_fileobj(f, BUCKET_MESSAGE_VOICES, file_name)

        logger.info(f"File {file_name} uploaded successfully to S3")
    except FileNotFoundError as e:
        logger.error(f"File {file_name} not found: {e}")
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error(f"Failed to upload file {file_name} to S3: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")
    finally:
        # Clean up the local file whether the upload was successful or not
        if os.path.exists(file_name):
            os.remove(file_name)
            logger.info(f"Local file {file_name} removed")

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

    try:
        with open(file_name, "rb") as f:
            s3_client.upload_fileobj(f, BUCKET_PROFILE_IMAGES, file_name)
        logger.info(f"File {file_name} uploaded successfully to S3")
    except Exception as e:
        logger.error(f"Failed to upload file {file_name} to S3: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")

    os.remove(file_name)
    return {"file_key": file_name}


@router.get("/get_file/{file_key}")
async def get_file(file_key: str, access_token: str = Depends(get_token)):

    BUCKETS = [BUCKET_MESSAGE_IMAGES, BUCKET_MESSAGE_VOICES]

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        db.commit()

    for bucket in BUCKETS:
        try:
            file_obj = s3_client.get_object(Bucket=bucket, Key=file_key)
            return StreamingResponse(
                file_obj['Body'],
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={file_key}"}
                )
        except Exception as e:
            logger.error(f"File not found in bucket {bucket}: {e}")

    raise HTTPException(status_code=404, detail=f"File with key {file_key} not found in any bucket")

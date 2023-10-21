import os
import traceback
import magic
from datetime import datetime
from typing import Optional, List, Union
from fastapi import UploadFile, File, APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse

from common.models.cities_models import City, Region
from common.models.user_models import User, UserPhoto, VerificationQueue
from common.schemas.service_schemas import VerificationUpdate, VerificationStatus
from common.utils.service_utils import send_event_to_socketio, send_push_notification
from common.utils.user_utils import get_user_push_token
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


@router.post("/upload/profile_photo")
async def upload_profile_image(
        file: UploadFile = File(...),
        is_avatar: Union[bool, str] = False,
        access_token: str = Depends(get_token)):
    if isinstance(is_avatar, str):
        is_avatar = is_avatar.lower() in ['true', '1', 'yes']

    with SessionLocal() as db:
        user_id = get_user_id_from_token(access_token)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        if is_avatar:
            current_avatar = db.query(UserPhoto).filter_by(user_id=user_id, is_avatar=True).first()
            if current_avatar:
                current_avatar.is_avatar = False
                db.commit()

        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(file.file.read(1024))
        file.file.seek(0)

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"profile_{user_id}_{timestamp}.{extension}"

        try:
            with open(file_name, "wb") as buffer:
                buffer.write(file.file.read())

            with open(file_name, "rb") as f:
                s3_client.upload_fileobj(f, BUCKET_PROFILE_IMAGES, file_name)

            photo_url = f"/service/get_file/{file_name}"
            new_photo = UserPhoto(
                user_id=user_id, photo_url=photo_url, is_avatar=is_avatar)
            db.add(new_photo)
            db.commit()

            photo_id = new_photo.id

        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to upload file")
        finally:
            if os.path.exists(file_name):
                os.remove(file_name)

    return {"id": photo_id, "file_key": file_name}


@router.get("/get_file/{file_key}")
async def get_file(file_key: str):

    BUCKETS = [BUCKET_MESSAGE_IMAGES, BUCKET_MESSAGE_VOICES, BUCKET_PROFILE_IMAGES]

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


@router.get("/cities", response_model=List[str])
async def get_cities(query: str):
    with SessionLocal() as db:
        try:
            query = query.lower().strip()
            query = "%" + query + "%"

            results = db.query(City.city_name, City.region_id, Region.name).join(Region, City.region_id == Region.id)\
                .filter(City.city_name.ilike(query)).limit(5).all()

            if not results:
                raise HTTPException(
                    status_code=404,
                    detail="Город не найден")

            city_counts = {}
            for result in results:
                city_name = result[0]
                city_counts[city_name] = city_counts.get(city_name, 0) + 1

            cities = []
            for result in results:
                city_name, region_id, region_name = result
                if city_counts[city_name] > 1:
                    city_name += f" ({region_name})"
                cities.append(city_name)

            return cities

        except Exception as e:
            print(f"Error occurred while querying the database: {e}")
            print(traceback.format_exc())
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка при запросе к базе данных")


@router.put("/verify/{user_id}")
async def update_verification_status(
        user_id: int,
        verification_update: VerificationUpdate) -> JSONResponse:
    with SessionLocal() as db:
        verification = db.query(VerificationQueue).filter(VerificationQueue.user_id == user_id).first()

        if not verification:
            logger.error("User not found in verification queue")
            raise HTTPException(status_code=404, detail="User not found in verification queue")

        verification.status = verification_update.status.value
        db.commit()

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error("User not found")
            raise HTTPException(status_code=404, detail="User not found")

        title = ""
        body = ""
        if verification_update.status == VerificationStatus.approved:
            user.verify = "approved"
            user.is_verified = True
            title = "Успешная верификация!"
            body = "Вы успешно верифицированы! Перезайдите в приложение."
        elif verification_update.status == VerificationStatus.denied:
            user.verify = "denied"
            user.is_verified = False
            title = "Неудачная верификация!"
            body = "Мы не смогли вас верифицировать. Отправьте нам фото для повторной верификации."
        else:
            logger.error("Invalid status")
            raise HTTPException(status_code=400, detail="Invalid status")

        db.commit()

        # Send push notification here
        push_token = await get_user_push_token(user_id)
        if push_token:
            await send_push_notification(push_token, title, body, data={}, aps={})

    logger.info(f"Sending event to socket: {verification_update.status.value}")

    event_data = {
        "user_id": user_id,
        "status": f"{verification_update.status.value}"
    }

    try:
        socketio_url = 'http://socket_app:1025?no-auth=True'
        event_name = 'update_verification_status'

        await send_event_to_socketio(socketio_url, event_name, event_data)
        logger.info("Event sent to socket successfully")
        logger.info(f"Event data: {event_data}, Event name: {event_name}")
    except Exception as e:
        logger.error(f"Error sending event to socket: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(
        content={
            "status": "success",
            "message": f"Verification status updated to {verification_update.status.value}"
        }
    )


@router.post("/send_sos_push")
async def send_sos_push(access_token: str = Depends(get_token)) -> JSONResponse:
    user_id = get_user_id_from_token(access_token)

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()

    if not user:
        logger.error("User not found")
        raise HTTPException(status_code=404, detail="User not found")

    push_token = await get_user_push_token(user_id)
    if push_token:
        title = "SOS push"
        body = "Ткни, чтобы перейти на SOS экран"
        await send_push_notification(push_token, title, body, data={}, aps={})
        logger.info(f"SOS push sent")
        return JSONResponse(content={"status": "success", "message": "SOS push sent"})

    logger.error("Push token not found")
    return JSONResponse(content={"status": "error", "message": "Push token not found"}, status_code=404)

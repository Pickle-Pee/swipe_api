import os
from fastapi import UploadFile, File, APIRouter
from fastapi.responses import StreamingResponse
from config import s3_client, BUCKET_NAME

router = APIRouter(prefix="/service", tags=["Auth Controller"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_name = file.filename
    with open(file_name, "wb") as buffer:
        buffer.write(file.file.read())

    with open(file_name, "rb") as f:
        s3_client.upload_fileobj(f, BUCKET_NAME, file_name)

    os.remove(file_name)

    return {"file_key": file_name}


@router.get("/get_file/{file_key}")
async def get_file(file_key: str):
    file_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_key)
    return StreamingResponse(file_obj['Body'],
                             media_type="application/octet-stream",
                             headers={"Content-Disposition": f"attachment; filename={file_key}"})

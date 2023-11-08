import socketio
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os
import logging
import boto3

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Environments configuration

load_dotenv()

os.environ["MYPYTHON"] = "True"

DATABASE_URL = os.getenv("DATABASE_URL")
ASYNC_DATABASE_URL = os.getenv("ASYNC_DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
DADATA_API_TOKEN = os.getenv("DADATA_API_TOKEN")
DADATA_API_SECRET = os.getenv("DADATA_API_SECRET")
DADATA_API_URL = os.getenv("DADATA_API_URL")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.getenv("REFRESH_TOKEN_EXPIRE_HOURS"))
YANDEX_KEY_ID = os.getenv("YANDEX_KEY_ID")
YANDEX_KEY = os.getenv("YANDEX_KEY")
BUCKET_MESSAGE_IMAGES = os.getenv("BUCKET_MESSAGE_IMAGES")
BUCKET_MESSAGE_VOICES = os.getenv("BUCKET_MESSAGE_VOICES")
BUCKET_PROFILE_IMAGES = os.getenv("BUCKET_PROFILE_IMAGES")
BUCKET_VERIFY_IMAGES = os.getenv("BUCKET_VERIFY_IMAGES")
SMS_API_KEY = os.getenv("SMS_API_KEY")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
VERIFY_CHAT_LINK=os.getenv("VERIFY_CHAT_LINK")
VERIFY_CHAT_ID=os.getenv("VERIFY_CHAT_ID")
VERIFY_SEND_TEXT=os.getenv("VERIFY_SEND_TEXT")
SMS_CENTER_LOGIN=os.getenv("SMS_CENTER_LOGIN")
SMS_CENTER_PASSWORD=os.getenv("SMS_CENTER_PASSWORD")
MAX_DISTANCE=os.getenv("MAX_DISTANCE")

# Logging configuration

logging.basicConfig(level=logging.DEBUG)
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logger = logging.getLogger(__name__)


class NoPingPongFilter(logging.Filter):
    def filter(self, record):
        # Исключите логи, содержащие строки 'PING' и 'PONG'
        return 'PING' not in record.msg and 'PONG' not in record.msg


engineio_logger = logging.getLogger('engineio')
engineio_logger.addFilter(NoPingPongFilter())

socketio_logger = logging.getLogger('socketio')
socketio_logger.addFilter(NoPingPongFilter())

# Database configuration

engine = create_engine(DATABASE_URL)
asyncEngine = create_async_engine(ASYNC_DATABASE_URL, echo=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(bind=asyncEngine, class_=AsyncSession, expire_on_commit=False,)

Base = declarative_base()

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*", logger=True, engineio_logger=True)
socket_app = socketio.ASGIApp(sio)

s3_client = boto3.client(
    's3',
    endpoint_url='https://storage.yandexcloud.net',
    aws_access_key_id=YANDEX_KEY_ID,
    aws_secret_access_key=YANDEX_KEY,
    # region_name=REGION_KEY
)

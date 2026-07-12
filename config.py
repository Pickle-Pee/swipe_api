import socketio
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os
import logging
import boto3
import redis
from pathlib import Path

load_dotenv()

redis_host = os.getenv('REDIS_HOST', 'redis')
redis_port = os.getenv('REDIS_PORT', 6379)

redis_client = redis.Redis(host=redis_host, port=redis_port, db=0)

origins = [
    "https://swagger.swipeapi.ru",
    "https://swipeapi.ru",
    "https://swipe-23679.web.app",
    "*"
]


def add_cors(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

os.environ["MYPYTHON"] = "True"

APP_ENV = os.getenv("APP_ENV", "development").lower()
if APP_ENV not in {"demo", "development", "production"}:
    raise RuntimeError("APP_ENV must be one of: demo, development, production")

IS_DEMO = APP_ENV == "demo"
IS_PRODUCTION = APP_ENV == "production"


def env_value(name, demo_default=None):
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    if IS_DEMO:
        return demo_default
    return None


DATABASE_URL = env_value("DATABASE_URL", "postgresql://swipe:swipe@localhost:5432/swipe_demo")
ASYNC_DATABASE_URL = env_value("ASYNC_DATABASE_URL", "postgresql+asyncpg://swipe:swipe@localhost:5432/swipe_demo")
SECRET_KEY = env_value("SECRET_KEY", "demo-secret-key-not-for-production")
DADATA_API_TOKEN = os.getenv("DADATA_API_TOKEN")
DADATA_API_SECRET = os.getenv("DADATA_API_SECRET")
DADATA_API_URL = os.getenv("DADATA_API_URL")
ACCESS_TOKEN_EXPIRE_MINUTES = int(env_value("ACCESS_TOKEN_EXPIRE_MINUTES", "30") or "30")
REFRESH_TOKEN_EXPIRE_HOURS = int(env_value("REFRESH_TOKEN_EXPIRE_HOURS", "168") or "168")
YANDEX_KEY_ID = os.getenv("YANDEX_KEY_ID")
YANDEX_KEY = os.getenv("YANDEX_KEY")
BUCKET_MESSAGE_IMAGES = os.getenv("BUCKET_MESSAGE_IMAGES")
BUCKET_MESSAGE_VOICES = os.getenv("BUCKET_MESSAGE_VOICES")
BUCKET_PROFILE_IMAGES = os.getenv("BUCKET_PROFILE_IMAGES")
BUCKET_VERIFY_IMAGES = os.getenv("BUCKET_VERIFY_IMAGES")
SMS_API_KEY = os.getenv("SMS_API_KEY")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
VERIFY_CHAT_LINK = os.getenv("VERIFY_CHAT_LINK")
VERIFY_CHAT_ID = os.getenv("VERIFY_CHAT_ID")
VERIFY_SEND_TEXT = os.getenv("VERIFY_SEND_TEXT")
SMS_CENTER_LOGIN = os.getenv("SMS_CENTER_LOGIN")
SMS_CENTER_PASSWORD = os.getenv("SMS_CENTER_PASSWORD")
MAX_DISTANCE = float(env_value("MAX_DISTANCE", "100") or "100")
OPEN_API_KEY = os.getenv("OPEN_API_KEY")
SMS_SENDER = os.getenv("SMS_SENDER")
TBANK_TERMINAL_PASSWORD = os.getenv("TBANK_TERMINAL_PASSWORD") or os.getenv("TBANK_KASSA_PASSWORD")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY") or os.getenv("TBANK_KASSA_TERMINAL")
TBANK_API_BASE_URL = env_value("TBANK_API_BASE_URL", "https://securepay.tinkoff.ru/v2")
TBANK_NOTIFICATION_URL = os.getenv("TBANK_NOTIFICATION_URL")
TBANK_SUCCESS_URL = os.getenv("TBANK_SUCCESS_URL")
TBANK_FAIL_URL = os.getenv("TBANK_FAIL_URL")
TBANK_RECURRENT_ENABLED = (os.getenv("TBANK_RECURRENT_ENABLED", "false").lower() == "true")
TBANK_HTTP_TIMEOUT_SECONDS = float(os.getenv("TBANK_HTTP_TIMEOUT_SECONDS", "10"))
# Temporary compatibility aliases for legacy code. New code uses the names above.
TBANK_KASSA_PASSWORD = TBANK_TERMINAL_PASSWORD
TBANK_KASSA_TERMINAL = TBANK_TERMINAL_KEY
PUSH_URL = env_value("PUSH_URL", "http://localhost:1026/send_push")
DEMO_STORAGE_DIR = Path(env_value("DEMO_STORAGE_DIR", ".demo_storage") or ".demo_storage")
DEMO_VERIFICATION_CODE = env_value("DEMO_VERIFICATION_CODE", "000000")

required_base = ["DATABASE_URL", "ASYNC_DATABASE_URL", "SECRET_KEY"]
required_production = required_base + [
    "DADATA_API_TOKEN", "DADATA_API_SECRET", "DADATA_API_URL",
    "YANDEX_KEY_ID", "YANDEX_KEY", "BUCKET_MESSAGE_IMAGES",
    "BUCKET_MESSAGE_VOICES", "BUCKET_PROFILE_IMAGES", "BUCKET_VERIFY_IMAGES",
    "SMS_CENTER_LOGIN", "SMS_CENTER_PASSWORD", "SMS_SENDER",
    "FIREBASE_CREDENTIALS_PATH", "TBANK_TERMINAL_PASSWORD", "TBANK_TERMINAL_KEY",
]
required_names = required_production if IS_PRODUCTION else ([] if IS_DEMO else required_base)
missing_names = [name for name in required_names if not globals().get(name)]
if missing_names:
    raise RuntimeError("Missing required environment variables: " + ", ".join(missing_names))

TKASSA_PUBLIC_KEY = "tkassa_public.pem"

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
AsyncSessionLocal = sessionmaker(bind=asyncEngine, class_=AsyncSession, expire_on_commit=False, )

Base = declarative_base()

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*", logger=True, engineio_logger=True)
socket_app = socketio.ASGIApp(sio)

class LocalStorageClient:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def upload_fileobj(self, file_obj, bucket, key):
        target = self.root / (bucket or "default") / Path(key).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            output.write(file_obj.read())

    def get_object(self, Bucket, Key):
        source = self.root / (Bucket or "default") / Path(Key).name
        return {"Body": source.open("rb")}


if IS_DEMO:
    BUCKET_MESSAGE_IMAGES = BUCKET_MESSAGE_IMAGES or "message-images"
    BUCKET_MESSAGE_VOICES = BUCKET_MESSAGE_VOICES or "message-voices"
    BUCKET_PROFILE_IMAGES = BUCKET_PROFILE_IMAGES or "profile-images"
    BUCKET_VERIFY_IMAGES = BUCKET_VERIFY_IMAGES or "verify-images"
    s3_client = LocalStorageClient(DEMO_STORAGE_DIR)
else:
    s3_client = boto3.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        aws_access_key_id=YANDEX_KEY_ID,
        aws_secret_access_key=YANDEX_KEY,
    )

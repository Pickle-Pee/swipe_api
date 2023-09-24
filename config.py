from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os
import logging
import boto3

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

load_dotenv()

os.environ["MYPYTHON"] = "True"

DATABASE_URL = os.getenv("DATABASE_URL")
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
# REGION_KEY = os.getenv("REGION_KEY")

logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

s3_client = boto3.client(
    's3',
    endpoint_url='https://storage.yandexcloud.net',
    aws_access_key_id=YANDEX_KEY_ID,
    aws_secret_access_key=YANDEX_KEY,
    # region_name=REGION_KEY
)


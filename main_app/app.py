import os

from fastapi import FastAPI

from config import engine, Base
from controllers.auth_controller import router as auth_router
from controllers.user_controller import router as user_router
from controllers.interests_controller import router as interests_router
from controllers.likes_controller import router as likes_router
from controllers.subscription_controller import router as subscription_router
from controllers.matches_controller import router as matches_router
from controllers.communication_controller import router as communication_router
from controllers.service_controller import router as service_router

# from common.models.auth_models import *
# from common.models.user_models import *
# from common.models.interests_models import *
# from common.models.cities_models import *
# from common.models.likes_models import *
from common.models.communication_models import *
# from common.models.error_models import *

app = FastAPI()

async def startup_event():
    # Создание всех таблиц в базе данных при старте приложения
    Base.metadata.create_all(bind=engine)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(interests_router)
app.include_router(likes_router)
app.include_router(subscription_router)
app.include_router(matches_router)
app.include_router(communication_router)
app.include_router(service_router)


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(app, host=app_host, port=1024)

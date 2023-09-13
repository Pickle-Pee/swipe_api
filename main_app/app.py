import os

import socketio
from fastapi import FastAPI
from controllers.auth_controller import router as auth_router
from controllers.user_controller import router as user_router
from controllers.interests_controller import router as interests_router
from controllers.likes_controller import router as likes_router
from controllers.subscription_controller import router as subscription_router
from controllers.matches_controller import router as matches_router
from controllers.communication_controller import router as communication_router
from common.utils.socket_utils import sio, socket_app

app = FastAPI()

app.mount("/socket.io", socket_app)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(interests_router)
app.include_router(likes_router)
app.include_router(subscription_router)
app.include_router(matches_router)
app.include_router(communication_router)

socket_app = socketio.ASGIApp(socketio_server=sio, other_asgi_app=app)

if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(socket_app, host=app_host, port=1024)

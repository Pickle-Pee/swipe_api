#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from fastapi import FastAPI
from main_app.controllers.auth_controller import router as auth_router
from main_app.controllers.user_controller import router as user_router
from main_app.controllers.interests_controller import router as interests_router
from matches_app.controllers.matches_controller import router as matches_router
from main_app.controllers.likes_controller import router as likes_router
from main_app.controllers.subscription_controller import router as subscription_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(interests_router)
app.include_router(matches_router)
app.include_router(likes_router)
app.include_router(subscription_router)

if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("APP_HOST")
    app_port = int(os.getenv("APP_PORT"))
    uvicorn.run(app, host=app_host, port=app_port)

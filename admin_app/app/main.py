from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, admin, users, interests, transactions, subscriptions, user_subscriptions

# Создание всех таблиц (используйте Alembic для миграций в продакшене)
app = FastAPI(
    title="Admin API for Dating Service",
    description="API для администрирования сервиса знакомств",
    version="1.0.0"
)

# Определите список разрешенных origins
# origins = [
#     "http://localhost:5137"
# ]

# Добавляем CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Включение маршрутов с общим префиксом /admin
app.include_router(auth.router, prefix="/admin/auth", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(users.router, prefix="/admin/users", tags=["users"])
app.include_router(subscriptions.router, prefix="/admin/subscriptions", tags=["subscriptions"])
app.include_router(interests.router, prefix="/admin/interests", tags=["interests"])
app.include_router(transactions.router, prefix="/admin/transactions", tags=["transactions"])
app.include_router(user_subscriptions.router, prefix="/admin/user_subscriptions", tags=["user_subscriptions"])


@app.get("/admin", summary="Проверка доступности админского API")
def read_root():
    return {"message": "Welcome to the Admin API"}

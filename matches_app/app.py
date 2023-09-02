import os
from fastapi import FastAPI
from controllers.matches_controller import router as matches_router

app = FastAPI()

app.include_router(matches_router)

if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MATCHES_APP_HOST")
    app_port = int(os.getenv("MATCHES_APP_PORT"))
    uvicorn.run(app, host=app_host, port=app_port)
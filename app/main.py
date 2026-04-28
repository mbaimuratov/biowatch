from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.web.routes import router as web_router


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    application.mount("/static", StaticFiles(directory="app/static"), name="static")
    application.include_router(web_router)
    application.include_router(router)
    return application


app = create_app()

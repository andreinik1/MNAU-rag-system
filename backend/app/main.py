from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.clients import cache_collection, collection
from app.core.config import settings
from app.routers.admin import router as admin_router
from app.routers.chat import router as chat_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Бэкенд RAG-системи Миколаївського національного аграрного університету (МНАУ) з семантичним кэшуванням та інкрементальною векторизацією.",
    version=settings.VERSION,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/")
def root():
    """Проверка жизнеспособности сервиса."""
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "vector_count": collection.count(),
        "cache_count": cache_collection.count(),
        "admin_panel": "/admin",
        "swagger_docs": "/docs",
        "message": "МНАУ RAG API з інкрементальною векторизацією працює!",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

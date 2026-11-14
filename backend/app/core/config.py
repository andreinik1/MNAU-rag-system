import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация проекта МНАУ RAG."""

    # Приложение
    PROJECT_NAME: str = "МНАУ RAG API"
    VERSION: str = "2.1.0"
    DEBUG: bool = False

    # OpenAI API
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    SIMILARITY_THRESHOLD: float = 0.12

    # ChromaDB
    COLLECTION_NAME: str = "mnau_knowledge_base"
    CACHE_COLLECTION_NAME: str = "semantic_cache"

    # Базовые пути проекта
    # backend/app/core/config.py -> core -> app -> backend
    BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent
    PROJECT_ROOT: Path = BACKEND_DIR.parent

    # Пути к данным
    DATA_DIR: Path = BACKEND_DIR / "data"
    RAW_DIR: Path = DATA_DIR / "raw"
    DOCUMENTS_DIR: Path = RAW_DIR / "documents"
    TEXTS_DIR: Path = RAW_DIR / "texts"
    CHROMA_PERSIST_DIR: Path = DATA_DIR / "vector_db"
    CHUNKS_FILE: Path = DATA_DIR / "processed_chunks.json"

    # Файлы ссылок скрапера
    WHITELISTED_PATHS_FILE: Path = PROJECT_ROOT / "whitelisted_paths.json"
    CLEANED_PATHS_FILE: Path = PROJECT_ROOT / "cleaned_paths.json"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=[
            str(Path(__file__).resolve().parent.parent.parent.parent / ".env"),
            str(Path(__file__).resolve().parent.parent.parent / ".env"),
            ".env",
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Если ключ не подтянулся из pydantic_settings напрямую, проверим os.getenv
if not settings.OPENAI_API_KEY:
    settings.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Создаем директории при необходимости
settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
settings.TEXTS_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)

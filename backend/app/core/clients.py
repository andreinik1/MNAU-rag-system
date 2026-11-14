import os
import chromadb
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv
from openai import OpenAI
from app.core.config import settings

load_dotenv()

print(f"🔄 [ChromaDB] Подключение к векторной базе: {settings.CHROMA_PERSIST_DIR}")
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))


def get_knowledge_collection() -> Collection:
    return chroma_client.get_or_create_collection(name=settings.COLLECTION_NAME)


def get_cache_collection() -> Collection:
    return chroma_client.get_or_create_collection(name=settings.CACHE_COLLECTION_NAME)


collection = get_knowledge_collection()
cache_collection = get_cache_collection()


def get_openai_client() -> OpenAI:
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ ОШИБКА: OPENAI_API_KEY не найден в переменных окружения!")
    return OpenAI(api_key=api_key)


openai_client = get_openai_client()

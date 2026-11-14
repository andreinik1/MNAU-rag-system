import os
import chromadb
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv
from openai import OpenAI
from app.core.config import settings

# Гарантируем загрузку переменных окружения
load_dotenv()

# Инициализация постоянного хранилища ChromaDB
print(f"🔄 [ChromaDB] Подключение к векторной базе: {settings.CHROMA_PERSIST_DIR}")
chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))

# Основная коллекция базы знаний университета
collection: Collection = chroma_client.get_or_create_collection(
    name=settings.COLLECTION_NAME
)

# Коллекция семантического кэша
cache_collection: Collection = chroma_client.get_or_create_collection(
    name=settings.CACHE_COLLECTION_NAME
)

# OpenAI клиент
def get_openai_client() -> OpenAI:
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ ОШИБКА: OPENAI_API_KEY не найден в переменных окружения!")
    return OpenAI(api_key=api_key)

openai_client = get_openai_client()

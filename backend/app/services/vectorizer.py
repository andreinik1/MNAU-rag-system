import json
import os
from pathlib import Path
import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class OpenAIVectorIndexer:

  def __init__(
      self,
      chunks_file: str = "backend/data/processed_chunks.json",
      db_persist_dir: str = "backend/data/vector_db",
      collection_name: str = "mnau_knowledge_base",
      model_name: str = "text-embedding-3-small",
  ):
    self.chunks_file = Path(chunks_file)
    self.db_persist_dir = db_persist_dir
    self.collection_name = collection_name
    self.model_name = model_name

    # Инициализация клиента OpenAI (ключ берется из .env файла)
    if "OPENAI_API_KEY" not in os.environ:
      print("⚠️ Внимание: Переменная окружения OPENAI_API_KEY не найдена!")
      print("Убедись, что она прописана в твоем .env файле.")

    self.openai_client = OpenAI()

    # Инициализация постоянного хранилища ChromaDB
    print("🔄 Инициализация локальной векторной базы данных ChromaDB...")
    self.client = chromadb.PersistentClient(path=self.db_persist_dir)

    # Создаем или получаем коллекцию
    self.collection = self.client.get_or_create_collection(
        name=self.collection_name
    )

  def load_chunks(self) -> list[dict]:
    """Загружает чанки из JSON-файла."""
    if not self.chunks_file.exists():
      print(f"❌ Файл с чанками {self.chunks_file} не найден!")
      return []

    print(f"📂 Загружаю чанки из {self.chunks_file}...")
    with open(self.chunks_file, "r", encoding="utf-8") as f:
      chunks = json.load(f)

    print(f"✅ Загружено чанков для индексации: {len(chunks)}")
    return chunks

  def get_openai_embeddings(self, texts: list[str]) -> list[list[float]]:
    """Отправляет батч текстов в OpenAI API и возвращает векторы."""
    response = self.openai_client.embeddings.create(
        input=texts, model=self.model_name
    )
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]

  def index_data(self, batch_size: int = 100):
    """Генерирует эмбеддинги через OpenAI и загружает в ChromaDB батчами."""
    chunks = self.load_chunks()
    if not chunks:
      return

    print(
        f"🚀 Начинаю векторизацию через модель {self.model_name} и загрузку в"
        " ChromaDB..."
    )

    total_chunks = len(chunks)
    for i in range(0, total_chunks, batch_size):
      batch = chunks[i : i + batch_size]

      ids = [item["chunk_id"] for item in batch]
      texts = [item["text"] for item in batch]

      # Очищаем метаданные (Chroma принимает только примитивные типы)
      metadatas = []
      for item in batch:
        meta = item.get("metadata", {})
        clean_meta = {k: (v if v is not None else "") for k, v in meta.items()}
        metadatas.append(clean_meta)

      try:
        # 1. Получаем векторы от OpenAI API
        embeddings = self.get_openai_embeddings(texts)

        # 2. Сохраняем в ChromaDB готовые векторы вместе с текстами и метаданными
        self.collection.upsert(
            ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
        )

        processed_count = min(i + batch_size, total_chunks)
        batch_num = i // batch_size + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size
        print(
            f"💾 Загружен батч {batch_num} / {total_batches} (обработано чанков:"
            f" {processed_count}/{total_chunks})"
        )

      except Exception as e:
        print(f"❌ Ошибка при обработке батча {i}: {e}")
        break

    print("\n🎉 Векторизация и индексация через OpenAI успешно завершены!")
    print(f"📂 Готовая база данных сохранена в папку: {self.db_persist_dir}")


if __name__ == "__main__":
  indexer = OpenAIVectorIndexer()
  indexer.index_data()
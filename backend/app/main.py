import json
import os
from chromadb import PersistentClient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
  raise RuntimeError("❌ ОШИБКА: OPENAI_API_KEY не найден в переменных окружения!")

app = FastAPI(
    title="МНАУ RAG API",
    description="Бэкенд чат-бота МНАУ с семантическим кэшированием",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация путей и клиентов
DB_PERSIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../backend/data/vector_db")
)
COLLECTION_NAME = "mnau_knowledge_base"
CACHE_COLLECTION_NAME = "semantic_cache"
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
# Порог похожести (чем меньше число, тем ближе смысл. 0.12 — отличный баланс для синонимов)
SIMILARITY_THRESHOLD = 0.12

print(f"🔄 Подключаемся к векторной базе по пути: {DB_PERSIST_DIR}")
chroma_client = PersistentClient(path=DB_PERSIST_DIR)

# Основная база знаний университета
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)
# Коллекция для семантического кэша (сохраняется на диск!)
cache_collection = chroma_client.get_or_create_collection(
    name=CACHE_COLLECTION_NAME
)

openai_client = OpenAI(api_key=api_key)


class ChatRequest(BaseModel):
  question: str


class SourceInfo(BaseModel):
  source_file: str
  source_url: str | None = None


class ChatResponse(BaseModel):
  answer: str
  sources: list[SourceInfo]
  from_cache: bool = False


@app.get("/")
def root():
  return {
      "status": "online",
      "vector_count": collection.count(),
      "cache_count": cache_collection.count(),
      "message": "МНАУ RAG API с семантическим кэшем работает!",
  }


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
  query = request.question.strip()
  if not query:
    raise HTTPException(status_code=400, detail="Запит не може бути порожнім.")

  try:
    # 1. Генерируем эмбеддинг для входящего вопроса
    response = openai_client.embeddings.create(
        input=[query], model=EMBEDDING_MODEL
    )
    query_embedding = response.data[0].embedding

    # 2. Пытаемся найти похожий вопрос в семантическом кэше
    cache_results = cache_collection.query(
        query_embeddings=[query_embedding], n_results=1
    )

    if cache_results and cache_results["distances"][0]:
      best_distance = cache_results["distances"][0][0]
      # Если нашли вопрос с близким смыслом
      if best_distance <= SIMILARITY_THRESHOLD:
        cached_meta = cache_results["metadatas"][0][0]
        cached_answer = cached_meta.get("answer")
        cached_sources = json.loads(cached_meta.get("sources_json", "[]"))

        print(
            f"⚡ [SEMANTIC CACHE HIT] Найден похожий вопрос (дистанция:"
            f" {best_distance:.4f}). Отдаем из кэша."
        )

        sources_list = [
            SourceInfo(
                source_file=s.get("source_file"), source_url=s.get("source_url")
            )
            for s in cached_sources
        ]
        return ChatResponse(
            answer=cached_answer, sources=sources_list, from_cache=True
        )

    print("🔍 [CACHE MISS] Идем в основную базу знаний и GPT...")

    # 3. Основной RAG-поиск, если в кэше ничего нет
    results = collection.query(query_embeddings=[query_embedding], n_results=4)

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    context_blocks = []
    sources_set = set()

    for doc, meta in zip(documents, metadatas):
      source = meta.get("source_file", "Документ МНАУ")
      url = meta.get("source_url", "")
      context_blocks.append(f"Джерело: {source} ({url})\nТекст:\n{doc}")
      sources_set.add((source, url))

    context = "\n\n---\n\n".join(context_blocks)

    # 4. Запрос к GPT-4o-mini
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ти — офіційний штучний інтелект-помічник Миколаївського"
                    " національного аграрного університету (МНАУ). Твоє завдання —"
                    " відповідати на запитання студентів та абітурієнтів ЧИТКО,"
                    " СТРУКТУРОВАНО і виключно на основі наданого нижче контексту"
                    " з офіційних документів університету. Якщо в контексті немає"
                    " відповіді, чесно скажи про це і порадь звернутися до"
                    " приймальної комісії або на офіційний сайт"
                    " https://www.mnau.edu.ua/."
                ),
            },
            {
                "role": "user",
                "content": f"Контекст з бази знань:\n{context}\n\nЗапитання: {query}",
            },
        ],
        temperature=0.2,
    )

    answer = completion.choices[0].message.content
    sources_list = [
        SourceInfo(source_file=s[0], source_url=s[1]) for s in sources_set
    ]

    # 5. Сохраняем новый вопрос и ответ в персистентный кэш ChromaDB
    import uuid

    cache_id = str(uuid.uuid4())
    sources_dicts = [{"source_file": s.source_file, "source_url": s.source_url} for s in sources_list]

    cache_collection.add(
        ids=[cache_id],
        embeddings=[query_embedding],
        documents=[query],  # Сохраняем текст исходного вопроса
        metadatas=[
            {
                "answer": answer,
                "sources_json": json.dumps(sources_dicts, ensure_ascii=False),
            }
        ],
    )

    return ChatResponse(answer=answer, sources=sources_list, from_cache=False)

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Помилка сервера: {str(e)}")
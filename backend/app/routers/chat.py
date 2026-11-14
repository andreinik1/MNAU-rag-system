import json
import uuid
from fastapi import APIRouter, HTTPException

from app.core.clients import cache_collection, collection, openai_client
from app.core.config import settings
from app.models.schemas import ChatRequest, ChatResponse, SourceInfo

router = APIRouter(prefix="/api", tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Основной эндпоинт чат-бота:
    1. Генерирует эмбеддинг вопроса
    2. Проверяет семантический кэш
    3. При промахе ищет в ChromaDB и генерирует ответ через GPT-4o-mini
    4. Кэширует новый ответ
    """
    query = request.question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Запит не може бути порожнім.")

    try:
        # 1. Генерируем эмбеддинг для входящего вопроса
        response = openai_client.embeddings.create(
            input=[query],
            model=settings.OPENAI_EMBEDDING_MODEL,
        )
        query_embedding = response.data[0].embedding

        # 2. Пытаемся найти похожий вопрос в семантическом кэше
        cache_results = cache_collection.query(
            query_embeddings=[query_embedding],
            n_results=1,
        )

        if cache_results and cache_results.get("distances") and cache_results["distances"][0]:
            best_distance = cache_results["distances"][0][0]
            if best_distance <= settings.SIMILARITY_THRESHOLD:
                cached_meta = cache_results["metadatas"][0][0]
                cached_answer = cached_meta.get("answer", "")
                cached_sources = json.loads(cached_meta.get("sources_json", "[]"))

                print(
                    f"⚡ [SEMANTIC CACHE HIT] Знайдено схоже питання (дистанція: {best_distance:.4f}). "
                    "Відповідь віддано з кэшу."
                )

                sources_list = [
                    SourceInfo(
                        source_file=s.get("source_file", ""),
                        source_url=s.get("source_url"),
                    )
                    for s in cached_sources
                ]
                return ChatResponse(
                    answer=cached_answer,
                    sources=sources_list,
                    from_cache=True,
                )

        print("🔍 [CACHE MISS] Звертаємося до бази знань ChromaDB та GPT...")

        # 3. Основной RAG-поиск в ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=4,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        context_blocks = []
        sources_set = set()

        for doc, meta in zip(documents, metadatas):
            source = meta.get("source_file", "Документ МНАУ")
            url = meta.get("source_url", "")
            context_blocks.append(f"Джерело: {source} ({url})\nТекст:\n{doc}")
            sources_set.add((source, url))

        context = "\n\n---\n\n".join(context_blocks)

        # 4. Запрос к GPT-4o-mini
        system_prompt = (
            "Ти — офіційний штучний інтелект-помічник Миколаївського національного аграрного університету (МНАУ). "
            "Твоє завдання — відповідати на запитання студентів та абітурієнтів ЧІТКО, СТРУКТУРОВАНО "
            "і виключно на основі наданого нижче контексту з офіційних документів університету. "
            "Якщо в контексті немає відповіді, чесно скажи про це і порадь звернутися до приймальної комісії "
            "або на офіційний сайт https://www.mnau.edu.ua/."
        )

        completion = openai_client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Контекст з бази знань:\n{context}\n\nЗапитання: {query}",
                },
            ],
            temperature=0.2,
        )

        answer = completion.choices[0].message.content or "Вибачте, не вдалося згенерувати відповідь."
        sources_list = [
            SourceInfo(source_file=s[0], source_url=s[1]) for s in sources_set
        ]

        # 5. Сохраняем в семантический кэш
        cache_id = str(uuid.uuid4())
        sources_dicts = [
            {"source_file": s.source_file, "source_url": s.source_url}
            for s in sources_list
        ]

        cache_collection.add(
            ids=[cache_id],
            embeddings=[query_embedding],
            documents=[query],
            metadatas=[
                {
                    "answer": answer,
                    "sources_json": json.dumps(sources_dicts, ensure_ascii=False),
                }
            ],
        )

        return ChatResponse(
            answer=answer,
            sources=sources_list,
            from_cache=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Помилка в chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Помилка сервера: {str(e)}")

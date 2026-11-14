import json
import re
import uuid
from typing import List, Set, Tuple
from fastapi import APIRouter, HTTPException

from app.core.clients import (
    get_cache_collection,
    get_knowledge_collection,
    openai_client,
)
from app.core.config import settings
from app.models.schemas import ChatRequest, ChatResponse, SourceInfo

router = APIRouter(prefix="/api", tags=["Chat"])

SCHEDULE_KEYWORDS = {
    "розклад",
    "розпис",
    "schedule",
    "пара",
    "пари",
    "пару",
    "парі",
    "занять",
    "заняття",
    "аудиторія",
    "аудиторії",
    "аудиторіях",
    "викладач",
    "викладає",
    "понеділок",
    "вівторок",
    "середа",
    "середу",
    "четвер",
    "п'ятниця",
    "п'ятницю",
    "пятниця",
    "субота",
}


def extract_group_code(text: str) -> str | None:
    """Извлекает код группы из вопроса (например, 'Кн 2/1', 'Мен 2/1', 'Б 2/1', 'А 2/2')."""
    match = re.search(r"\b([А-Яа-яІіЇїЄєA-Za-z]{1,4} ?\d+/\d+)\b", text)
    if match:
        raw = match.group(1).strip()
        # Нормализуем одиночный пробел перед номером
        parts = re.split(r"\s+", raw)
        if len(parts) == 2:
            return f"{parts[0]} {parts[1]}"
        return raw
    return None


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Основной эндпоинт чат-бота:
    1. Генерирует эмбеддинг вопроса
    2. Проверяет семантический кэш
    3. Применяет гибридную маршрутизацию:
       - Если вопрос про расписание/группу -> целевой поиск по метаданным расписания
       - Основной RAG-поиск по всей базе знань
    4. Генерирует точный ответ через GPT-4o-mini
    5. Кэширует результат
    """
    query = request.question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Запит не може бути порожнім.")

    try:
        cache_collection = get_cache_collection()
        collection = get_knowledge_collection()

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

        # 3. Интеллектуальный RAG-поиск
        query_lower = query.lower()
        extracted_group = extract_group_code(query)
        is_schedule_query = bool(extracted_group) or any(k in query_lower for k in SCHEDULE_KEYWORDS)

        collected_docs: List[str] = []
        collected_metas: List[dict] = []
        seen_texts: Set[str] = set()

        # А. Если указана группа -> точечный поиск по метаданным группы
        if extracted_group:
            print(f"🎯 [Routing] Виявлено запит розкладу для групи: '{extracted_group}'")
            try:
                grp_res = collection.query(
                    query_embeddings=[query_embedding],
                    where={"group": extracted_group},
                    n_results=2,
                )
                if grp_res and grp_res.get("documents") and grp_res["documents"][0]:
                    for d, m in zip(grp_res["documents"][0], grp_res["metadatas"][0]):
                        if d not in seen_texts:
                            seen_texts.add(d)
                            collected_docs.append(d)
                            collected_metas.append(m)
            except Exception as e:
                print(f"⚠️ Помилка пошуку по групі: {e}")

        # Б. Если вопрос касается расписания в целом -> подтягиваем чанки расписаний
        if is_schedule_query and len(collected_docs) < 3:
            try:
                sched_res = collection.query(
                    query_embeddings=[query_embedding],
                    where={"category": "schedule"},
                    n_results=3,
                )
                if sched_res and sched_res.get("documents") and sched_res["documents"][0]:
                    for d, m in zip(sched_res["documents"][0], sched_res["metadatas"][0]):
                        if d not in seen_texts:
                            seen_texts.add(d)
                            collected_docs.append(d)
                            collected_metas.append(m)
            except Exception as e:
                print(f"⚠️ Помилка пошуку по розкладу: {e}")

        # В. Основной семантический поиск по всей базе
        remaining_slots = max(4, 6 - len(collected_docs))
        general_res = collection.query(
            query_embeddings=[query_embedding],
            n_results=remaining_slots,
        )

        if general_res and general_res.get("documents") and general_res["documents"][0]:
            for d, m in zip(general_res["documents"][0], general_res["metadatas"][0]):
                if d not in seen_texts:
                    seen_texts.add(d)
                    collected_docs.append(d)
                    collected_metas.append(m)

        # 4. Формирование контекста и источников
        context_blocks = []
        sources_set = set()

        for doc, meta in zip(collected_docs, collected_metas):
            source = meta.get("source_file", "Документ МНАУ")
            url = meta.get("source_url", "")
            context_blocks.append(f"Джерело: {source} ({url})\nТекст:\n{doc}")
            sources_set.add((source, url))

        context = "\n\n---\n\n".join(context_blocks)

        # 5. Генерация ответа через GPT-4o-mini
        system_prompt = (
            "Ти — офіційний штучний інтелект-помічник Миколаївського національного аграрного університету (МНАУ). "
            "Твоє завдання — відповідати на запитання студентів та абітурієнтів ЧІТКО, СТРУКТУРОВАНО "
            "і виключно на основі наданого нижче контексту з офіційних документів та розкладу занять університету.\n\n"
            "Якщо в контексті є структурований розклад занять (дні, пари, аудиторії, викладачі), "
            "надавай відповідь чітким списком із зазначенням номера пари, назви дисципліни, ПІБ викладача та аудиторії.\n"
            "Якщо в контексті немає відповіді на питання, ввічливо повідом про це та порадь звернутися "
            "до деканату, приймальної комісії або на офіційний сайт https://www.mnau.edu.ua/."
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

        # 6. Сохраняем в семантический кэш
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

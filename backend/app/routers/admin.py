import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.clients import cache_collection, chroma_client, collection
from app.core.config import settings
from app.models.schemas import (
    StatsResponse,
    SyncResponse,
    UploadResponse,
    UrlScrapeRequest,
)
from app.services.scraper import scraper_service
from app.services.vectorizer import vectorizer_service

router = APIRouter(tags=["Admin"])

# Шаблоны Jinja2
TEMPLATES_DIR = settings.BACKEND_DIR / "app" / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".rtf",
    ".json",
    ".txt",
    ".csv",
}


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    """Отображение визуальной веб-панели администратора."""
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "project_name": settings.PROJECT_NAME,
            "version": settings.VERSION,
        },
    )


@router.get("/api/admin/stats", response_model=StatsResponse)
def get_stats():
    """Получение текущей статистики базы знаний и хранилища."""
    try:
        total_vectors = collection.count()
        cached_queries = cache_collection.count()
        processed_files = len(vectorizer_service.get_processed_source_files())

        raw_docs = len(
            [
                f
                for f in settings.DOCUMENTS_DIR.iterdir()
                if f.is_file() and not f.name.startswith(".")
            ]
        ) if settings.DOCUMENTS_DIR.exists() else 0

        raw_texts = len(
            [
                f
                for f in settings.TEXTS_DIR.iterdir()
                if f.is_file() and f.suffix.lower() == ".json"
            ]
        ) if settings.TEXTS_DIR.exists() else 0

        return StatsResponse(
            total_vectors=total_vectors,
            cached_queries=cached_queries,
            processed_files_count=processed_files,
            raw_documents_count=raw_docs,
            raw_texts_count=raw_texts,
            embedding_model=settings.OPENAI_EMBEDDING_MODEL,
            chat_model=settings.OPENAI_CHAT_MODEL,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка отримання статистики: {e}")


@router.post("/api/admin/upload-file", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="Файл для завантаження (PDF, XLSX, DOCX, RTF, JSON)"),
    category: Optional[str] = Form("document", description="Категорія (document, schedule, admissions)"),
    force: bool = Form(False, description="Примусово оновити ембеддинги, якщо файл вже оброблено"),
):
    """
    Инкрементальная загрузка и обработка нового файла:
    1. Сохраняет файл в raw/documents/ (или raw/texts/ для JSON)
    2. Проверяет processed_chunks.json
    3. Выполняет чанкинг ТОЛЬКО для нового файла
    4. Проверяет ChromaDB и индексирует ТОЛЬКО новые чанки (0 токенов на старые)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Ім'я файлу не може бути порожнім.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Непідтримуваний формат файлу '{ext}'. Дозволені: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Определяем целевую папку
    target_dir = settings.TEXTS_DIR if ext == ".json" else settings.DOCUMENTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Безопасное имя файла
    safe_filename = os.path.basename(file.filename)
    target_path = target_dir / safe_filename

    try:
        # Сохраняем файл на диск
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Запускаем инкрементальный пайплайн
        result = vectorizer_service.process_and_index_file(
            file_path=target_path,
            category=category or "document",
            force=force,
        )

        return UploadResponse(**result)

    except Exception as e:
        print(f"❌ Помилка під час завантаження файлу: {e}")
        raise HTTPException(status_code=500, detail=f"Помилка обробки файлу: {str(e)}")


@router.post("/api/admin/sync", response_model=SyncResponse)
def sync_database(
    force: bool = Query(False, description="Примусово перевірити всі чанки з базою"),
):
    """
    Синхронизация всех сырых файлов (raw/documents и raw/texts) с ChromaDB.
    Находит все не обработанные файлы, создает чанки и индексирует только недостающие векторы.
    """
    try:
        result = vectorizer_service.sync_raw_data(force=force)
        return SyncResponse(**result)
    except Exception as e:
        print(f"❌ Помилка синхронізації: {e}")
        raise HTTPException(status_code=500, detail=f"Помилка синхронізації: {str(e)}")


@router.post("/api/admin/scrape-url", response_model=UploadResponse)
def scrape_and_index_url(payload: UrlScrapeRequest):
    """
    Скачивание отдельной веб-страницы/документа по URL и инкрементальная индексация.
    """
    url = payload.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Некоректний URL (має починатися з http:// або https://)")

    saved_file = scraper_service.scrape_single_url(url)
    if not saved_file or not saved_file.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Не вдалося завантажити вміст за посиланням {url}. Перевірте доступність ресурсу.",
        )

    try:
        result = vectorizer_service.process_and_index_file(
            file_path=saved_file,
            category=payload.category or "web_page",
            force=payload.force,
            source_url=url,
        )
        return UploadResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка векторизації URL: {str(e)}")


@router.post("/api/admin/cache/clear")
def clear_cache():
    """Очистка семантического кэша запросов."""
    try:
        global cache_collection
        # Удаляем и создаем заново коллекцию кэша
        chroma_client.delete_collection(name=settings.CACHE_COLLECTION_NAME)
        cache_collection = chroma_client.get_or_create_collection(
            name=settings.CACHE_COLLECTION_NAME
        )
        return {"status": "success", "message": "Семантичний кєш успішно очищено."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка очищення кэшу: {str(e)}")


@router.get("/api/admin/files")
def get_files_list(limit: int = Query(100, ge=1, le=500)):
    """Получение списка обработанных файлов для админки."""
    try:
        files = vectorizer_service.get_files_overview(limit=limit)
        return {"total": len(files), "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка отримання списку файлів: {str(e)}")

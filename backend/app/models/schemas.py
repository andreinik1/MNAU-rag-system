from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="Питання користувача для чат-бота")


class SourceInfo(BaseModel):
    source_file: str = Field(..., description="Назва файлу або назва сторінки")
    source_url: Optional[str] = Field(None, description="URL-посилання, якщо доступне")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Згенерована відповідь асистента")
    sources: List[SourceInfo] = Field(default_factory=list, description="Джерела інформації")
    from_cache: bool = Field(False, description="Чи отримана відповідь із семантичного кэшу")


class DocumentChunk(BaseModel):
    chunk_id: str
    document_title: str
    text: str
    metadata: Dict[str, Any]


class UploadResponse(BaseModel):
    status: str = Field(..., description="'indexed' | 'already_processed' | 'skipped' | 'error'")
    filename: str
    message: str
    chunks_created: int = 0
    chunks_indexed: int = 0
    chunks_skipped: int = 0
    total_vectors_in_db: int = 0


class SyncResponse(BaseModel):
    status: str
    message: str
    files_scanned: int = 0
    new_files_processed: int = 0
    new_chunks_created: int = 0
    new_chunks_indexed: int = 0
    chunks_skipped: int = 0
    total_vectors_in_db: int = 0
    duration_seconds: float = 0.0


class ClearScheduleResponse(BaseModel):
    status: str = Field(..., description="'success' | 'error'")
    message: str
    deleted_from_db: int = 0
    deleted_from_json: int = 0
    cache_cleared: int = 0
    deleted_files: List[str] = []
    total_vectors_in_db: int = 0


class StatsResponse(BaseModel):
    total_vectors: int
    cached_queries: int
    processed_files_count: int
    raw_documents_count: int
    raw_texts_count: int
    embedding_model: str
    chat_model: str


class UrlScrapeRequest(BaseModel):
    url: str = Field(..., description="URL-адреса сторінки сайту університету")
    category: Optional[str] = Field("web_page", description="Категорія документа")
    force: bool = Field(False, description="Примусово оновити, якщо вже існує")

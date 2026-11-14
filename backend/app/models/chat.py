# Re-export schemas for backward compatibility
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    SourceInfo,
    DocumentChunk,
)

__all__ = ["ChatRequest", "ChatResponse", "SourceInfo", "DocumentChunk"]

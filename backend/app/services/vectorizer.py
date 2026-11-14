import json
import os
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
import chromadb
from chromadb.api.models.Collection import Collection
from openai import OpenAI

from app.core.clients import chroma_client, collection, openai_client
from app.core.config import settings
from app.models.schemas import DocumentChunk
from app.services.parser import AdvancedDocumentParser


class OpenAIVectorIndexer:
    """Сервис для инкрементальной векторизации документов и синхронизации с ChromaDB."""

    def __init__(
        self,
        chunks_file: Path | str = settings.CHUNKS_FILE,
        db_persist_dir: Path | str = settings.CHROMA_PERSIST_DIR,
        collection_name: str = settings.COLLECTION_NAME,
        model_name: str = settings.OPENAI_EMBEDDING_MODEL,
        custom_openai_client: OpenAI | None = None,
        custom_chroma_collection: Collection | None = None,
    ):
        self.chunks_file = Path(chunks_file)
        self.db_persist_dir = Path(db_persist_dir)
        self.collection_name = collection_name
        self.model_name = model_name

        self.openai_client = custom_openai_client or openai_client
        self.collection = custom_chroma_collection or collection
        self.parser = AdvancedDocumentParser()

    def get_processed_source_files(self) -> Set[str]:
        """
        Возвращает множество имен файлов и заголовков (source_file),
        которые уже были обработаны и сохранены в processed_chunks.json.
        """
        if not self.chunks_file.exists():
            return set()

        processed: Set[str] = set()
        try:
            with open(self.chunks_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)

            for chunk in chunks:
                meta = chunk.get("metadata", {})
                sf = meta.get("source_file")
                if sf:
                    processed.add(sf.strip())
                    # Также сохраняем базовое имя файла без путей
                    processed.add(os.path.basename(sf).strip())

                dt = chunk.get("document_title")
                if dt:
                    processed.add(dt.strip())
                    processed.add(os.path.basename(dt).strip())

            return processed
        except Exception as e:
            print(f"⚠️ Помилка читання {self.chunks_file}: {e}")
            return set()

    def get_existing_chunk_ids(self, chunk_ids: List[str]) -> Set[str]:
        """
        Проверяет наличие chunk_id в ChromaDB с минимальным оверхедом
        через collection.get(ids=..., include=[]).
        ChromaDB возвращает ТОЛЬКО существующие IDs без выгрузки эмбеддингов и документов.
        """
        if not chunk_ids:
            return set()

        existing_ids: Set[str] = set()
        # Батчуем проверку по 500 ID для надежности и скорости
        batch_size = 500
        for i in range(0, len(chunk_ids), batch_size):
            batch = chunk_ids[i : i + batch_size]
            try:
                result = self.collection.get(ids=batch, include=[])
                found = result.get("ids", [])
                if found:
                    existing_ids.update(found)
            except Exception as e:
                print(f"⚠️ Помилка перевірки chunk_ids у ChromaDB: {e}")

        return existing_ids

    def get_openai_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Отправляет батч текстов в OpenAI Embeddings API и возвращает векторы."""
        if not texts:
            return []

        response = self.openai_client.embeddings.create(
            input=texts,
            model=self.model_name,
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    def index_chunks(
        self, chunks: List[Dict[str, Any]], batch_size: int = 100
    ) -> Tuple[int, int]:
        """
        Инкрементальная индексация списка чанков:
        1. Сверяет chunk_id с ChromaDB через collection.get(include=[])
        2. Исключает уже существующие чанки
        3. Отправляет в OpenAI ТОЛЬКО НОВЫЕ чанки
        4. Делает upsert в коллекцию
        Возвращает: (indexed_count, skipped_count)
        """
        if not chunks:
            return 0, 0

        all_ids = [c["chunk_id"] for c in chunks]
        existing_ids = self.get_existing_chunk_ids(all_ids)

        new_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]
        skipped_count = len(chunks) - len(new_chunks)

        if not new_chunks:
            print(
                f"⚡ Всі {len(chunks)} чанків вже присутні у ChromaDB. Токени OpenAI збережено (0 токенів витрачено)!"
            )
            return 0, skipped_count

        print(
            f"🚀 Нових чанків для векторизації: {len(new_chunks)} (пропущено існуючих: {skipped_count})"
        )

        indexed_count = 0
        total_new = len(new_chunks)

        for i in range(0, total_new, batch_size):
            batch = new_chunks[i : i + batch_size]
            batch_texts = [item["text"] for item in batch]
            batch_ids = [item["chunk_id"] for item in batch]

            metadatas = []
            for item in batch:
                meta = item.get("metadata", {})
                clean_meta = {k: (v if v is not None else "") for k, v in meta.items()}
                metadatas.append(clean_meta)

            try:
                # Генерируем эмбеддинги ТОЛЬКО для нового среза
                embeddings = self.get_openai_embeddings(batch_texts)

                # Сохраняем в ChromaDB
                self.collection.upsert(
                    ids=batch_ids,
                    embeddings=embeddings,
                    documents=batch_texts,
                    metadatas=metadatas,
                )
                indexed_count += len(batch)
                batch_num = (i // batch_size) + 1
                total_batches = (total_new + batch_size - 1) // batch_size
                print(
                    f"💾 Завантажено батч {batch_num}/{total_batches} (+{len(batch)} векторів у ChromaDB)"
                )
            except Exception as e:
                print(f"❌ Помилка при векторизації батча {i}: {e}")
                raise e

        return indexed_count, skipped_count

    def append_to_processed_chunks(
        self, new_chunks: List[Dict[str, Any]], replace_source: str | None = None
    ) -> None:
        """Атомарно добавляет новые чанки в processed_chunks.json."""
        existing: List[Dict[str, Any]] = []
        if self.chunks_file.exists():
            try:
                with open(self.chunks_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception as e:
                print(f"⚠️ Не вдалося прочитати існуючий {self.chunks_file}: {e}")
                existing = []

        if replace_source:
            # Если принудительное обновление, удаляем старые чанки данного файла
            existing = [
                c
                for c in existing
                if c.get("metadata", {}).get("source_file") != replace_source
                and c.get("document_title") != replace_source
            ]

        existing.extend(new_chunks)

        # Атомарная запись через временный файл
        temp_file = self.chunks_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        temp_file.replace(self.chunks_file)

    def process_and_index_file(
        self,
        file_path: Path | str,
        category: str = "document",
        force: bool = False,
        source_url: str = "",
    ) -> Dict[str, Any]:
        """
        Инкрементальный пайплайн для одного файла:
        a. Проверяет, обработан ли файл ранее в processed_chunks.json
        b. Запускает чанкинг только для нового файла
        c. Перед вызовом OpenAI API сверяет chunk_id с ChromaDB
        """
        path = Path(file_path)
        filename = path.name

        processed_files = self.get_processed_source_files()

        # 1. Проверяем, был ли файл обработан ранее
        if not force and (filename in processed_files or filename.strip() in processed_files):
            return {
                "status": "already_processed",
                "filename": filename,
                "message": (
                    f"Файл '{filename}' вже оброблено раніше (знайдено у processed_chunks.json). "
                    "Обробку пропущено для економії токенів OpenAI."
                ),
                "chunks_created": 0,
                "chunks_indexed": 0,
                "chunks_skipped": 0,
                "total_vectors_in_db": self.collection.count(),
            }

        # 2. Чанкинг только для нового файла
        chunks = self.parser.process_file(
            file_path=str(path),
            category=category,
            source_url=source_url,
        )

        if not chunks:
            return {
                "status": "error",
                "filename": filename,
                "message": f"Не вдалося витягти текст або сформувати чанки з файлу '{filename}'.",
                "chunks_created": 0,
                "chunks_indexed": 0,
                "chunks_skipped": 0,
                "total_vectors_in_db": self.collection.count(),
            }

        chunk_dicts = [c.model_dump() for c in chunks]

        # 3. Сохраняем новые чанки в processed_chunks.json
        self.append_to_processed_chunks(
            chunk_dicts,
            replace_source=filename if force else None,
        )

        # 4. Инкрементально векторизуем через ChromaDB & OpenAI
        indexed_count, skipped_count = self.index_chunks(chunk_dicts)

        return {
            "status": "indexed",
            "filename": filename,
            "message": (
                f"Файл '{filename}' успішно оброблено! Створено чанків: {len(chunks)}, "
                f"нових векторів у ChromaDB: {indexed_count}, "
                f"пропущено існуючих дублікатів: {skipped_count}."
            ),
            "chunks_created": len(chunks),
            "chunks_indexed": indexed_count,
            "chunks_skipped": skipped_count,
            "total_vectors_in_db": self.collection.count(),
        }

    def sync_raw_data(self, force: bool = False) -> Dict[str, Any]:
        """
        Инкрементальная синхронизация всех файлов из raw/documents и raw/texts:
        - Находит не обработанные файлы
        - Чанкует только их
        - Проверяет ChromaDB и дописывает только недостающие эмбеддинги
        """
        import time

        start_time = time.time()
        processed_files = self.get_processed_source_files()

        all_raw_files: List[Tuple[Path, str]] = []

        if settings.DOCUMENTS_DIR.exists():
            for f in settings.DOCUMENTS_DIR.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    all_raw_files.append((f, "document"))

        if settings.TEXTS_DIR.exists():
            for f in settings.TEXTS_DIR.iterdir():
                if f.is_file() and f.suffix.lower() == ".json":
                    all_raw_files.append((f, "web_page"))

        # Фильтруем файлы, которые нужно обработать
        files_to_process = []
        for file_path, category in all_raw_files:
            if force or file_path.name not in processed_files:
                files_to_process.append((file_path, category))

        print(
            f"📊 [Sync] Всього файлів на диску: {len(all_raw_files)}, "
            f"потребують обробки: {len(files_to_process)}"
        )

        total_new_chunks = 0
        new_chunks_accumulator: List[Dict[str, Any]] = []

        for fpath, cat in files_to_process:
            chunks = self.parser.process_file(str(fpath), category=cat)
            if chunks:
                chunk_dicts = [c.model_dump() for c in chunks]
                new_chunks_accumulator.extend(chunk_dicts)
                total_new_chunks += len(chunk_dicts)

        total_indexed = 0
        total_skipped = 0

        if new_chunks_accumulator:
            self.append_to_processed_chunks(new_chunks_accumulator)
            total_indexed, total_skipped = self.index_chunks(new_chunks_accumulator)

        duration = round(time.time() - start_time, 2)

        return {
            "status": "success",
            "message": (
                f"Синхронізація успішна за {duration} с. "
                f"Перевірено файлів: {len(all_raw_files)}, оброблено нових: {len(files_to_process)}, "
                f"створено чанків: {total_new_chunks}, додано векторів: {total_indexed}, "
                f"пропущено існуючих: {total_skipped}."
            ),
            "files_scanned": len(all_raw_files),
            "new_files_processed": len(files_to_process),
            "new_chunks_created": total_new_chunks,
            "new_chunks_indexed": total_indexed,
            "chunks_skipped": total_skipped,
            "total_vectors_in_db": self.collection.count(),
            "duration_seconds": duration,
        }

    def get_files_overview(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Возвращает сводку по обработанным файлам для отображения в админке."""
        if not self.chunks_file.exists():
            return []

        try:
            with open(self.chunks_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)

            files_map: Dict[str, Dict[str, Any]] = {}
            for chunk in chunks:
                meta = chunk.get("metadata", {})
                sf = meta.get("source_file") or chunk.get("document_title") or "Невідомий файл"
                if sf not in files_map:
                    files_map[sf] = {
                        "source_file": sf,
                        "category": meta.get("category", "document"),
                        "chunk_count": 0,
                        "source_url": meta.get("source_url", ""),
                    }
                files_map[sf]["chunk_count"] += 1

            result = list(files_map.values())
            # Сортируем: сначала документы, затем по числу чанков
            result.sort(key=lambda x: x["chunk_count"], reverse=True)
            return result[:limit]
        except Exception as e:
            print(f"⚠️ Помилка зведення файлів: {e}")
            return []


# Глобальный инстанс индексатора
vectorizer_service = OpenAIVectorIndexer()

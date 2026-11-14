import hashlib
import json
import os
from pathlib import Path
from typing import List, Optional
from bs4 import BeautifulSoup
from docx import Document
import pandas as pd
from pypdf import PdfReader
from striprtf.striprtf import rtf_to_text

from app.models.schemas import DocumentChunk


class AdvancedDocumentParser:
    """Универсальный парсер документов (PDF, XLSX, DOCX, RTF, JSON веб-страниц)."""

    @staticmethod
    def parse_pdf(file_path: str) -> str:
        """Извлекает текст из PDF-файла."""
        try:
            reader = PdfReader(file_path)
            text_blocks = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_blocks.append(f"\n--- Сторінка {i + 1} ---\n{page_text.strip()}")
            return "\n".join(text_blocks)
        except Exception as e:
            print(f"❌ Помилка при парсингу PDF {file_path}: {e}")
            return ""

    @staticmethod
    def parse_excel(file_path: str) -> str:
        """Конвертирует Excel-таблицы (.xlsx, .xls) в структурированный Markdown."""
        try:
            xls = pd.ExcelFile(file_path)
            markdown_parts = []
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                df = df.dropna(how="all").dropna(axis=1, how="all")
                if not df.empty:
                    markdown_parts.append(f"\n\n### Аркуш: {sheet_name}\n")
                    markdown_parts.append(df.to_markdown(index=False))
            return "\n".join(markdown_parts)
        except Exception as e:
            print(f"❌ Помилка при парсингу Excel таблиці {file_path}: {e}")
            return ""

    @staticmethod
    def parse_docx(file_path: str) -> str:
        """Извлекает текст и таблицы из Word (.docx) файлов."""
        try:
            doc = Document(file_path)
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            
            # Также извлекаем таблицы из docx
            table_texts = []
            for table in doc.tables:
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_data:
                        table_texts.append(" | ".join(row_data))

            full_text = "\n".join(paragraphs)
            if table_texts:
                full_text += "\n\n### Таблиці документа:\n" + "\n".join(table_texts)
            return full_text
        except Exception as e:
            print(f"❌ Помилка при парсингу DOCX {file_path}: {e}")
            return ""

    @staticmethod
    def parse_rtf(file_path: str) -> str:
        """Извлекает текст из RTF файлов."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return rtf_to_text(content)
        except Exception as e:
            print(f"❌ Помилка при парсингу RTF {file_path}: {e}")
            return ""

    @staticmethod
    def parse_json_web(file_path: str) -> tuple[str, str, str]:
        """Извлекает контент, заголовок и url из скрапленного JSON-файла."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("content", ""), data.get("title", ""), data.get("url", "")
        except Exception as e:
            print(f"❌ Помилка читання JSON {file_path}: {e}")
            return "", "", ""

    @staticmethod
    def parse_plain_text(file_path: str) -> str:
        """Извлекает текст из обычных текстовых файлов (.txt, .md, .csv)."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            print(f"❌ Помилка читання текстового файлу {file_path}: {e}")
            return ""

    def process_file(
        self,
        file_path: str | Path,
        category: str = "document",
        source_url: str = "",
    ) -> List[DocumentChunk]:
        """Определяет тип файла, извлекает текст и разбивает на чанки."""
        path = Path(file_path)
        if not path.exists():
            print(f"❌ Файл не знайдено: {file_path}")
            return []

        file_extension = path.suffix.lower()
        raw_text = ""
        document_title = path.name

        # Автоопределение категории, если не задана явно
        if category in ["general", "document"]:
            name_lower = path.name.lower()
            if any(k in name_lower for k in ["schedule", "rozklad", "розпис", "розклад"]):
                category = "schedule"
            elif any(k in name_lower for k in ["bachelor", "vstup", "вступ", "pk", "admission", "pravyla"]):
                category = "admissions"

        try:
            if file_extension == ".json":
                content, title, url = self.parse_json_web(str(path))
                raw_text = content
                if title:
                    document_title = title
                if url:
                    source_url = url
                category = "web_page"
            elif file_extension == ".pdf":
                raw_text = self.parse_pdf(str(path))
            elif file_extension in [".xlsx", ".xls"]:
                raw_text = self.parse_excel(str(path))
            elif file_extension == ".docx":
                raw_text = self.parse_docx(str(path))
            elif file_extension == ".rtf":
                raw_text = self.parse_rtf(str(path))
            elif file_extension in [".txt", ".md", ".csv"]:
                raw_text = self.parse_plain_text(str(path))
            else:
                print(f"⚠️ Формат {file_extension} не підтримується для парсингу.")
                return []
        except Exception as e:
            print(f"❌ Помилка під час обробки {file_path}: {e}")
            return []

        if not raw_text or not raw_text.strip():
            print(f"⚠️ Текст у файлі {path.name} порожній або не вдалося прочитати.")
            return []

        return self.chunk_text(
            text=raw_text,
            document_title=document_title,
            category=category,
            file_path=str(path),
            source_url=source_url,
        )

    @staticmethod
    def chunk_text(
        text: str,
        document_title: str,
        category: str,
        file_path: str = "",
        source_url: str = "",
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> List[DocumentChunk]:
        """Разбивает текст на перекрывающиеся чанки и создает DocumentChunk с детерминированным MD5 id."""
        chunks: List[DocumentChunk] = []
        start = 0
        text_length = len(text)
        chunk_index = 0

        # Нормализуем пробелы и символы перевода строк
        text = text.replace("\x00", "")

        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_text = text[start:end]

            # Уникальный хеш: путь к файлу + индекс чанка + сам текст
            unique_string = f"{file_path}_{chunk_index}_{chunk_text}"
            chunk_id = hashlib.md5(unique_string.encode("utf-8")).hexdigest()

            chunk = DocumentChunk(
                chunk_id=chunk_id,
                document_title=document_title,
                text=chunk_text,
                metadata={
                    "category": category,
                    "faculty": "all",
                    "source_file": document_title,
                    "source_url": source_url or "",
                },
            )
            chunks.append(chunk)

            start += chunk_size - overlap
            chunk_index += 1

        return chunks

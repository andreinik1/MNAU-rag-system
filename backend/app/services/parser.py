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
from app.services.table_parser import (
    PDFTableExtractor,
    ScheduleParser,
    clean_cell_text,
    is_schedule_content,
)


class AdvancedDocumentParser:
    """
    Универсальный парсер документов:
    - Интеллектуальное распознавание расписаний занятий и генерация погрупповых карточек
    - Преобразование таблиц PDF, DOCX и XLSX в структурированный Markdown
    - Поддержка RTF, JSON веб-страниц, TXT
    """

    @staticmethod
    def parse_pdf_generic(file_path: str) -> str:
        """Извлечение таблиц в формате Markdown и текста с помощью pdfplumber."""
        try:
            extracted = PDFTableExtractor.extract_tables_and_text(file_path)
            if extracted and extracted.strip():
                return extracted
        except Exception as e:
            print(f"⚠️ Помилка pdfplumber ({file_path}), виконується fallback на pypdf: {e}")

        # Fallback на pypdf
        try:
            reader = PdfReader(file_path)
            text_blocks = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_blocks.append(f"\n--- Сторінка {i + 1} ---\n{page_text.strip()}")
            return "\n".join(text_blocks)
        except Exception as e:
            print(f"❌ Помилка fallback pypdf {file_path}: {e}")
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
        """Извлекает текст и конвертирует таблицы Word (.docx) в Markdown."""
        try:
            doc = Document(file_path)
            parts = []

            # Параграфы текста
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            if paragraphs:
                parts.append("\n".join(paragraphs))

            # Таблицы docx в виде Markdown
            for t_idx, table in enumerate(doc.tables, 1):
                table_rows = []
                for row in table.rows:
                    row_data = [clean_cell_text(cell.text) for cell in row.cells]
                    if any(row_data):
                        table_rows.append(row_data)

                if table_rows:
                    num_cols = max(len(r) for r in table_rows)
                    normalized = [r + [""] * (num_cols - len(r)) for r in table_rows]
                    header = normalized[0]
                    sep = ["---"] * num_cols
                    body = normalized[1:]

                    md_lines = [
                        f"\n### Таблиця {t_idx} (Word документ):",
                        "| " + " | ".join(header) + " |",
                        "| " + " | ".join(sep) + " |",
                    ]
                    for row in body:
                        md_lines.append("| " + " | ".join(row) + " |")

                    parts.append("\n".join(md_lines))

            return "\n\n".join(parts)
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
        """
        Универсальный пайплайн:
        1. Автоопределение типа (расписание, таблицы, текст)
        2. Если расписание: генерирует погрупповые и подневные структурированные чанки
        3. Если таблицы: преобразует в Markdown-таблицы
        4. Если текст: нарезает с перекрытием
        """
        path = Path(file_path)
        if not path.exists():
            print(f"❌ Файл не знайдено: {file_path}")
            return []

        file_extension = path.suffix.lower()
        document_title = path.name

        # 1. Автоопределение категории
        name_lower = path.name.lower()
        if category in ["general", "document", "tables"]:
            if is_schedule_content(name_lower, filename=path.name):
                category = "schedule"
            elif any(k in name_lower for k in ["bachelor", "vstup", "вступ", "pk", "admission", "pravyla"]):
                category = "admissions"

        # 2. Если это PDF и определено расписание — запускаем специализированный генератор чанков
        if file_extension == ".pdf" and category == "schedule":
            print(f"🗓️ [Schedule] Запуск структурованого парсера розкладу для {path.name}...")
            schedule_chunks = ScheduleParser.generate_chunks(
                pdf_path=path,
                document_title=document_title,
                source_url=source_url,
            )
            if schedule_chunks:
                print(f"✅ [Schedule] Успішно створено {len(schedule_chunks)} структурованих карток розкладу!")
                return schedule_chunks
            print("⚠️ Спеціалізований парсер розкладу не знайшов стандартної сітки, перехід на універсальний табличний парсер.")

        # 3. Обработка остальных форматов
        raw_text = ""

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
                raw_text = self.parse_pdf_generic(str(path))
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
        chunk_size: int = 1200,
        overlap: int = 250,
    ) -> List[DocumentChunk]:
        """Разбивает текст на чанки с перекрытием, сохраняя границы строк при возможности."""
        chunks: List[DocumentChunk] = []
        start = 0
        text_length = len(text)
        chunk_index = 0

        text = text.replace("\x00", "")

        while start < text_length:
            end = min(start + chunk_size, text_length)

            # Пытаемся разбить по границе параграфа или строки, если не конец текста
            if end < text_length:
                last_newline = text.rfind("\n", start + chunk_size // 2, end)
                if last_newline != -1:
                    end = last_newline

            chunk_text = text[start:end].strip()

            if chunk_text:
                unique_string = f"{file_path}_{chunk_index}_{chunk_text[:80]}"
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

            start = end - overlap if end < text_length else text_length
            if start < 0:
                start = 0
            chunk_index += 1

        return chunks

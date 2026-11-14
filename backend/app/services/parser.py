import hashlib
import json
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup
from docx import Document
import pandas as pd
from pydantic import BaseModel
from pypdf import PdfReader
from striprtf.striprtf import rtf_to_text


class DocumentChunk(BaseModel):
  chunk_id: str
  document_title: str
  text: str
  metadata: dict


class AdvancedDocumentParser:

  @staticmethod
  def parse_pdf(file_path: str) -> str:
    """Извлекает текст из PDF-файла."""
    try:
      reader = PdfReader(file_path)
      text = ""
      for i, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
          text += f"\n--- Страница {i + 1} ---\n" + page_text
      return text
    except Exception as e:
      return f"Ошибка при парсинге PDF {file_path}: {e}"

  @staticmethod
  def parse_excel(file_path: str) -> str:
    """Конвертирует Excel-таблицы в текст с разметкой Markdown."""
    try:
      xls = pd.ExcelFile(file_path)
      markdown_text = ""
      for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        markdown_text += f"\n\n### Лист: {sheet_name}\n"
        markdown_text += df.to_markdown(index=False)
      return markdown_text
    except Exception as e:
      return f"Ошибка при парсинге Excel таблицы {file_path}: {e}"

  @staticmethod
  def parse_docx(file_path: str) -> str:
    """Извлекает текст из Word (.docx) файлов."""
    try:
      doc = Document(file_path)
      return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
      return f"Ошибка при парсинге DOCX {file_path}: {e}"

  @staticmethod
  def parse_rtf(file_path: str) -> str:
    """Извлекает текст из RTF файлов."""
    try:
      with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
      return rtf_to_text(content)
    except Exception as e:
      return f"Ошибка при парсинге RTF {file_path}: {e}"

  def process_file(
      self, file_path: str, category: str = "general"
  ) -> List[DocumentChunk]:
    """Универсальный метод: определяет формат файла и запускает нужный парсер."""
    path = Path(file_path)
    file_extension = path.suffix.lower()
    raw_text = ""
    document_title = path.name
    source_url = ""

    try:
      # 1. Обработка JSON-файлов с веб-страниц (из папки texts/)
      if file_extension == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
          data = json.load(f)
        raw_text = data.get("content", "")
        document_title = data.get("title", path.name)
        source_url = data.get("url", "")

      # 2. Обработка документов (из папки documents/)
      elif file_extension == ".pdf":
        raw_text = self.parse_pdf(file_path)
      elif file_extension in [".xlsx", ".xls"]:
        raw_text = self.parse_excel(file_path)
      elif file_extension == ".docx":
        raw_text = self.parse_docx(file_path)
      elif file_extension == ".rtf":
        raw_text = self.parse_rtf(file_path)
      else:
        print(f"⚠️ Формат {file_extension} не поддерживается.")
        return []

    except Exception as e:
      print(f"❌ Ошибка чтения файла {file_path}: {e}")
      return []

    if not raw_text or not raw_text.strip():
      return []

    return self.chunk_text(
        text=raw_text,
        document_title=document_title,
        category=category,
        file_path=file_path,
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
    """Режет сплошной текст на чанки с перекрытием и генерирует уникальный ID."""
    chunks = []
    start = 0
    text_length = len(text)
    chunk_index = 0

    while start < text_length:
      end = min(start + chunk_size, text_length)
      chunk_text = text[start:end]

      # Железобетонная уникальность: путь к файлу + порядковый номер + текст
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
              "source_url": source_url,
          },
      )
      chunks.append(chunk)
      
      start += chunk_size - overlap
      chunk_index += 1

    return chunks
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests
import urllib3

# Отключаем предупреждения об SSL-сертификатах вуза
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class UniversityScraper:

  def __init__(
      self,
      paths_file: str = "cleaned_paths.json",
      save_dir: str = "backend/data/raw",
  ):
    self.paths_file = Path(paths_file)
    self.save_dir = Path(save_dir)
    self.save_dir.mkdir(parents=True, exist_ok=True)

    self.text_dir = self.save_dir / "texts"
    self.docs_dir = self.save_dir / "documents"
    self.text_dir.mkdir(parents=True, exist_ok=True)
    self.docs_dir.mkdir(parents=True, exist_ok=True)

    self.headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    self.document_extensions = (
        ".pdf",
        ".xlsx",
        ".xls",
        ".docx",
        ".doc",
        ".rtf",
        ".zip",
        ".rar",
    )

  def load_paths(self) -> list[str]:
    """Загружает и уникализирует список путей из JSON-файла."""
    if not self.paths_file.exists():
      print(f"❌ Файл {self.paths_file} не найден!")
      return []
    with open(self.paths_file, "r", encoding="utf-8") as f:
      paths = json.load(f)

    # Убираем дубликаты через set, сохраняя порядок
    unique_paths = list(dict.fromkeys(paths))
    print(
        f"📁 Загружено путей: {len(paths)} (уникальных после фильтра:"
        f" {len(unique_paths)})"
    )
    return unique_paths

  def clean_html_text(self, soup: BeautifulSoup) -> str:
    """Очищает HTML-страницу от мусора и удаляет управляющие символы."""
    for element in soup(
        ["script", "style", "nav", "footer", "header", "aside", "noscript"]
    ):
      element.decompose()
    text = soup.get_text(separator="\n")

    # Убираем нулевые байты и лишние пробелы, которые ломают JSON/базы
    text = text.replace("\x00", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

  def run(self):
    urls = self.load_paths()
    if not urls:
      return

    print(f"🚀 Запуск обхода и скачивания для {len(urls)} путей...")
    success_texts = 0
    success_docs = 0
    skipped_count = 0

    for i, url in enumerate(urls, 1):
      parsed_path = urlparse(url).path.lower()

      if i % 10 == 0:
        print(
            f"⏳ Прогресс: {i}/{len(urls)} | Текстов: {success_texts} |"
            f" Документов: {success_docs}"
        )

      time.sleep(0.1)  # Вежливая пауза для слабого вузовского сервера

      # 1. Скачивание прямых документов
      if parsed_path.endswith(self.document_extensions):
        if self._download_document(url):
          success_docs += 1
        else:
          skipped_count += 1
        continue

      # 2. Обработка веб-страниц (HTML)
      try:
        response = requests.get(
            url,
            headers=self.headers,
            timeout=10,
            allow_redirects=True,
            verify=False,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        # Проверка типа контента: пропускаем явные бинарные файлы (картинки, архивы),
        # но пропускаем страницы даже если заголовок content-type пустой (частая болезнь старых сайтов)
        content_type = response.headers.get("content-type", "").lower()
        if content_type and any(
            bad in content_type
            for bad in ["image/", "video/", "audio/", "application/zip"]
        ):
          skipped_count += 1
          continue

        soup = BeautifulSoup(response.text, "html.parser")

        title = ""
        if soup.title and soup.title.string:
          title = soup.title.string.strip()

        clean_text = self.clean_html_text(soup)

        if not clean_text or len(clean_text) < 30:
          skipped_count += 1
          continue

        # Сохранение в JSON
        safe_name = hashlib.md5(url.encode("utf-8")).hexdigest() + ".json"
        file_path = self.text_dir / safe_name

        page_data = {"url": url, "title": title, "content": clean_text}

        with open(file_path, "w", encoding="utf-8") as f:
          json.dump(page_data, f, ensure_ascii=False, indent=4)

        success_texts += 1

      except Exception:
        skipped_count += 1
        continue

    print(f"\n✅ Скрапинг успешно завершен!")
    print(f"📄 Сохранено текстовых страниц: {success_texts}")
    print(f"📁 Сохранено скачанных документов: {success_docs}")
    print(f"⚠️ Пропущено/ошибок: {skipped_count}")

  def _download_document(self, full_url: str) -> bool:
    file_name = os.path.basename(urlparse(full_url).path)
    if not file_name or "." not in file_name:
      file_name = "document.bin"
    else:
      name_part, ext_part = os.path.splitext(file_name)
      file_name = name_part[:80] + ext_part

    url_hash = hashlib.md5(full_url.encode("utf-8")).hexdigest()[:8]
    unique_file_name = f"{url_hash}_{file_name}"
    file_path = self.docs_dir / unique_file_name

    if file_path.exists():
      return True

    try:
      file_response = requests.get(
          full_url,
          headers=self.headers,
          timeout=15,
          allow_redirects=True,
          verify=False,
      )
      file_response.raise_for_status()
      with open(file_path, "wb") as f:
        f.write(file_response.content)
      return True
    except Exception:
      return False


if __name__ == "__main__":
  scraper = UniversityScraper(paths_file="cleaned_paths.json")
  scraper.run()
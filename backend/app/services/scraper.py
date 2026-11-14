import hashlib
import json
import os
from pathlib import Path
import time
from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests
import urllib3

from app.core.config import settings

# Отключаем предупреждения об SSL-сертификатах вуза
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class UniversityScraper:
    """Скрапер официального сайта МНАУ и связанных поддоменов."""

    def __init__(
        self,
        paths_file: Path | str = settings.CLEANED_PATHS_FILE,
        save_dir: Path | str = settings.RAW_DIR,
    ):
        self.paths_file = Path(paths_file)
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.text_dir = settings.TEXTS_DIR
        self.docs_dir = settings.DOCUMENTS_DIR
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

    def scrape_single_url(self, url: str) -> Optional[Path]:
        """
        Скачивает и сохраняет одиночный URL (веб-страницу или документ).
        Возвращает Path сохраненного файла либо None при ошибке.
        """
        parsed = urlparse(url)
        path_lower = parsed.path.lower()

        # 1. Если это прямой документ
        if path_lower.endswith(self.document_extensions):
            file_name = os.path.basename(parsed.path)
            if not file_name or "." not in file_name:
                file_name = "document.bin"
            else:
                name_part, ext_part = os.path.splitext(file_name)
                file_name = name_part[:80] + ext_part

            url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
            target_file = self.docs_dir / f"{url_hash}_{file_name}"

            try:
                resp = requests.get(
                    url,
                    headers=self.headers,
                    timeout=15,
                    allow_redirects=True,
                    verify=False,
                )
                resp.raise_for_status()
                with open(target_file, "wb") as f:
                    f.write(resp.content)
                return target_file
            except Exception as e:
                print(f"❌ Ошибка скачивания документа {url}: {e}")
                return None

        # 2. Если это HTML страница
        try:
            resp = requests.get(
                url,
                headers=self.headers,
                timeout=12,
                allow_redirects=True,
                verify=False,
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding

            content_type = resp.headers.get("content-type", "").lower()
            if content_type and any(
                bad in content_type
                for bad in ["image/", "video/", "audio/", "application/zip"]
            ):
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else parsed.path
            clean_text = self.clean_html_text(soup)

            if not clean_text or len(clean_text) < 30:
                print(f"⚠️ Текст со страницы {url} слишком короткий или пустой.")
                return None

            safe_name = hashlib.md5(url.encode("utf-8")).hexdigest() + ".json"
            target_file = self.text_dir / safe_name

            page_data = {"url": url, "title": title, "content": clean_text}
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(page_data, f, ensure_ascii=False, indent=4)

            return target_file
        except Exception as e:
            print(f"❌ Ошибка скрапинга URL {url}: {e}")
            return None

    def run(self):
        """Пакетный запуск скрапинга всех путей из cleaned_paths.json."""
        urls = self.load_paths()
        if not urls:
            return

        print(f"🚀 Запуск обхода и скачивания для {len(urls)} путей...")
        success_texts = 0
        success_docs = 0
        skipped_count = 0

        for i, url in enumerate(urls, 1):
            if i % 25 == 0:
                print(
                    f"⏳ Прогресс: {i}/{len(urls)} | Текстов: {success_texts} |"
                    f" Документов: {success_docs}"
                )

            time.sleep(0.05)
            saved = self.scrape_single_url(url)
            if saved:
                if saved.suffix.lower() == ".json":
                    success_texts += 1
                else:
                    success_docs += 1
            else:
                skipped_count += 1

        print(f"\n✅ Скрапинг успешно завершен!")
        print(f"📄 Сохранено текстовых страниц: {success_texts}")
        print(f"📁 Сохранено скачанных документов: {success_docs}")
        print(f"⚠️ Пропущено/ошибок: {skipped_count}")


# Глобальный экземпляр скрапера
scraper_service = UniversityScraper()

if __name__ == "__main__":
    scraper_service.run()

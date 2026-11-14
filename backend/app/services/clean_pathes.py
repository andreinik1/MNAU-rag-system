import json
import re
from pathlib import Path
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """Проверка валидности URL."""
    if " " in url or "\ufffd" in url:
        return False

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        path = parsed.path
        if "http://" in path or "https://" in path or "http:/" in path or "https:/" in path:
            return False

        external_sub_pattern = r"/(www\.(?!mnau\.edu\.ua)[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"
        if re.search(external_sub_pattern, path):
            return False

        if "https-www" in path or "http-www" in path:
            return False

        if path.endswith("\\") or url.endswith("‎"):
            return False

        return True
    except Exception:
        return False


def clean_links(input_file: str | Path, output_file: str | Path):
    """Фильтрация мусорных и битых ссылок."""
    input_p = Path(input_file)
    output_p = Path(output_file)

    if not input_p.exists():
        print(f"❌ Вхідний файл {input_p} не знайдено.")
        return

    with open(input_p, "r", encoding="utf-8") as f:
        links = json.load(f)

    cleaned_links = []
    trash_links = []

    for link in links:
        if is_valid_url(link):
            cleaned_links.append(link)
        else:
            trash_links.append(link)

    print(f"Исходное количество ссылок: {len(links)}")
    print(f"Удалено мусорных ссылок: {len(trash_links)}")
    print(f"Итоговое количество корректных ссылок: {len(cleaned_links)}")

    with open(output_p, "w", encoding="utf-8") as f:
        json.dump(cleaned_links, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    from app.core.config import settings

    clean_links(settings.WHITELISTED_PATHS_FILE, settings.CLEANED_PATHS_FILE)

import asyncio
from collections import deque
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

# Наш жесткий whitelist полезных поддоменов
ALLOWED_DOMAINS = {
    "www.mnau.edu.ua",
    "mnau.edu.ua",
    "pk.mnau.edu.ua",
    "lib.mnau.edu.ua",
    "graduate.mnau.edu.ua",
    "int.mnau.edu.ua",
    "startup.mnau.edu.ua",
    "konkurs.mnau.edu.ua",
}

# Ключевые слова для фильтрации новостного и мусорного шума
BLOCKED_KEYWORDS = [
    "/news/",
    "/novyny/",
    "/category/",
    "/tag/",
    "/author/",
    "/page/",
    "/search/",
    "wp-content",
    "wp-includes",
]

# Расширения файлов и статики, которые пропускаем на этапе сбора путей
SKIP_EXTENSIONS = (
    ".pdf",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".jpg",
    ".jpeg",
    ".png",
    ".zip",
    ".rar",
    ".css",
    ".js",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Стартовые точки для каждого разрешенного домена
initial_queue = [f"https://{domain}" for domain in ALLOWED_DOMAINS]
queue = deque(initial_queue)
visited_urls = set()
discovered_urls = set()


async def crawl_worker(client: httpx.AsyncClient, semaphore: asyncio.Semaphore):
  while queue:
    url = None
    try:
      url = queue.popleft()
    except IndexError:
      await asyncio.sleep(0.3)
      continue

    if url in visited_urls:
      continue

    visited_urls.add(url)
    print(f"[Найдено полезных путей: {len(discovered_urls)}] Обхожу: {url}")

    async with semaphore:
      try:
        response = await client.get(
            url, headers=HEADERS, timeout=10, follow_redirects=True
        )
        if response.status_code != 200:
          continue

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
          continue

        soup = BeautifulSoup(response.text, "html.parser")

        for link in soup.find_all("a", href=True):
          href = link["href"].strip()
          if not href or href.startswith(
              ("#", "javascript:", "mailto:", "tel:")
          ):
            continue

          full_url = urljoin(url, href)
          parsed = urlparse(full_url)
          netloc = parsed.netloc.lower()
          path = parsed.path.lower()

          # Проверяем строгое соответствие нашему whitelist поддоменов
          if netloc in ALLOWED_DOMAINS:
            # Фильтруем мусор и новости
            if any(kw in path for kw in BLOCKED_KEYWORDS):
              continue

            if path.endswith(SKIP_EXTENSIONS):
              continue

            clean_url = f"{parsed.scheme}://{netloc}{parsed.path}".rstrip("/")

            discovered_urls.add(clean_url)

            if clean_url not in visited_urls and clean_url not in queue:
              queue.append(clean_url)

      except Exception:
        continue

    await asyncio.sleep(0.05)


async def main():
  print(
      "🚀 Запуск целевого сборщика путей по строгому whitelist поддоменов..."
  )

  semaphore = asyncio.Semaphore(20)

  async with httpx.AsyncClient() as client:
    workers = [crawl_worker(client, semaphore) for _ in range(6)]
    await asyncio.gather(*workers)

  print(
      "\n✅ Сбор путей завершен! Всего уникальных полезных страниц:"
      f" {len(discovered_urls)}"
  )

  output_file = "whitelisted_paths.json"
  with open(output_file, "w", encoding="utf-8") as f:
    json.dump(sorted(list(discovered_urls)), f, ensure_ascii=False, indent=4)

  print(f"📁 Чистая карта путей сохранена в файл: {output_file}")


if __name__ == "__main__":
  asyncio.run(main())
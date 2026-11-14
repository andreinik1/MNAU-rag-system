import asyncio
from collections import deque
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

BASE_URL = "https://www.mnau.edu.ua"
DOMAIN = "mnau.edu.ua"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

visited_urls = set()
queue = deque([BASE_URL])
unique_subdomains = set()

# Чтобы краулер не застревал в бесконечных новостях при поиске поддоменов
SKIP_PATHS = (
    "/news/",
    "/novyny/",
    "/category/",
    "/tag/",
    "/author/",
    "/page/",
    "/search/",
    "wp-content",
)
SKIP_EXT = (
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
)


async def worker(client: httpx.AsyncClient, semaphore: asyncio.Semaphore):
  while queue:
    try:
      url = queue.popleft()
    except IndexError:
      await asyncio.sleep(0.2)
      continue

    if url in visited_urls:
      continue
    visited_urls.add(url)

    async with semaphore:
      try:
        response = await client.get(
            url, headers=HEADERS, timeout=8, follow_redirects=True
        )
        if response.status_code != 200:
          continue

        if "text/html" not in response.headers.get("content-type", "").lower():
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

          # Проверяем, что это домен или поддомен mnau.edu.ua
          if netloc == DOMAIN or netloc.endswith(f".{DOMAIN}"):
            # Сохраняем сам поддомен (без http/https и без пути)
            if netloc not in unique_subdomains:
              unique_subdomains.add(netloc)
              print(f"🔥 Новый поддомен [{len(unique_subdomains)}]: {netloc}")

            # Добавляем страницу в очередь, чтобы искать дальше (игнорируя файлы и мусор)
            if any(p in path for p in SKIP_PATHS) or path.endswith(SKIP_EXT):
              continue

            clean_url = (
                f"{parsed.scheme}://{netloc}{parsed.path}".rstrip("/")
            )
            if (
                clean_url not in visited_urls
                and clean_url not in queue
                and len(visited_urls) < 1500
            ):
              queue.append(clean_url)

      except Exception:
        continue

    await asyncio.sleep(0.05)


async def main():
  print("🔍 Ищем все уникальные поддомены *.mnau.edu.ua...")

  semaphore = asyncio.Semaphore(20)
  async with httpx.AsyncClient() as client:
    workers = [worker(client, semaphore) for _ in range(5)]
    await asyncio.gather(*workers)

  result = sorted(list(unique_subdomains))

  with open("subdomains.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

  print(f"\n✅ Готово! Всего найдено поддоменов: {len(result)}")
  for sub in result:
    print(f" - {sub}")


if __name__ == "__main__":
  asyncio.run(main())
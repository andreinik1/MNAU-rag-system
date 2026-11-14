import os
from chromadb import PersistentClient
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Проверяем наличие ключа OpenAI
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
  print("❌ ОШИБКА: Переменная OPENAI_API_KEY не найдена в файле .env!")
  exit(1)


def ask_rag(query: str):
  db_persist_dir = "backend/data/vector_db"
  collection_name = "mnau_knowledge_base"
  model_name = "text-embedding-3-small"

  print("🔄 Подключаемся к векторной базе ChromaDB...")
  client = PersistentClient(path=db_persist_dir)
  collection = client.get_collection(name=collection_name)

  print(f"📊 Всего элементов в базе: {collection.count()}")
  print(f"\n🔍 Запрос пользователя: «{query}»")

  # 1. Генерируем эмбеддинг для запроса через OpenAI
  openai_client = OpenAI(api_key=api_key)
  response = openai_client.embeddings.create(input=[query], model=model_name)
  query_embedding = response.data[0].embedding

  # 2. Ищем топ-4 самых релевантных чанка в ChromaDB
  results = collection.query(
      query_embeddings=[query_embedding],
      n_results=4,
  )

  documents = results["documents"][0]
  metadatas = results["metadatas"][0]

  # 3. Собираем контекст из найденных чанков
  context_blocks = []
  for doc, meta in zip(documents, metadatas):
    source = meta.get("source_file", "Неизвестный источник")
    url = meta.get("source_url", "")
    context_blocks.append(f"Джерело: {source} ({url})\nТекст:\n{doc}")

  context = "\n\n---\n\n".join(context_blocks)

  print("🤖 Формируем ответ через GPT-4o-mini...")

  # 4. Отправляем контекст и вопрос в GPT-4o-mini
  completion = openai_client.chat.completions.create(
      model="gpt-4o-mini",
      messages=[
          {
              "role": "system",
              "content": (
                  "Ти — офіційний штучний інтелект-помічник Миколаївського"
                  " національного аграрного університету (МНАУ). Твоє завдання —"
                  " відповідати на запитання студентів та абітурієнтів ЧІТКО,"
                  " СТРУКТУРОВАНО і виключно на основі наданого нижче контексту"
                  " з офіційних документів університету. Якщо в контексті немає"
                  " відповіді, чесно скажи про це і порадь звернутися до"
                  " приймальної комісії або на сайт https://www.mnau.edu.ua/."
                  " Обов'язково посилайся на джерела, якщо це доречно."
              ),
          },
          {
              "role": "user",
              "content": f"Контекст з бази знань:\n{context}\n\nЗапитання: {query}",
          },
      ],
      temperature=0.2,
  )

  answer = completion.choices[0].message.content

  print("\n" + "=" * 60)
  print("🎯 ОТВЕТ БОТА (GPT-4o-mini):")
  print("=" * 60)
  print(answer)
  print("=" * 60)


if __name__ == "__main__":
  # Можешь менять вопрос на любой другой
  test_query = "Як поселитися в гуртожиток МНАУ?"
  ask_rag(test_query)
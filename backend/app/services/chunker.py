import json
from pathlib import Path
from parser import AdvancedDocumentParser, DocumentChunk


class DataChunker:

  def __init__(
      self,
      raw_data_dir: str = "backend/data/raw",
      output_file: str = "backend/data/processed_chunks.json",
  ):
    self.raw_dir = Path(raw_data_dir)
    self.texts_dir = self.raw_dir / "texts"
    self.docs_dir = self.raw_dir / "documents"
    
    self.output_file = Path(output_file)
    self.output_file.parent.mkdir(parents=True, exist_ok=True)
    
    self.parser = AdvancedDocumentParser()

  def process_all(self):
    """Проходит по всем сырым текстам и документам, режет их на чанки

    и сохраняет в единый JSON-файл.
    """
    all_chunks: list[DocumentChunk] = []

    # 1. Обрабатываем JSON-страницы из папки texts/
    if self.texts_dir.exists():
      json_files = list(self.texts_dir.glob("*.json"))
      print(f"📄 Найдено JSON-страниц для чанкинга: {len(json_files)}")

      for i, file_path in enumerate(json_files, 1):
        chunks = self.parser.process_file(str(file_path), category="web_page")
        all_chunks.extend(chunks)
        if i % 100 == 0:
          print(f"Обработано веб-страниц: {i}/{len(json_files)}")

    # 2. Обрабатываем бинарные документы из папки documents/ (PDF, Excel, DOCX, RTF)
    if self.docs_dir.exists():
      doc_files = [
          f
          for f in self.docs_dir.iterdir()
          if f.is_file() and not f.name.startswith(".")
      ]
      print(f"📁 Найдено документов для чанкинга: {len(doc_files)}")

      for file_path in doc_files:
        # Автоматически определяем категорию по имени файла
        category = "document"
        file_lower = file_path.name.lower()
        if "schedule" in file_lower or "распис" in file_lower:
          category = "schedule"
        elif "bachelor" in file_lower or "pk" in file_lower or "admission" in file_lower:
          category = "admissions"

        chunks = self.parser.process_file(str(file_path), category=category)
        all_chunks.extend(chunks)

    print(f"\n🎉 Всего успешно сформировано чанков: {len(all_chunks)}")

    # 3. Сериализуем Pydantic-модели в обычные словари и сохраняем в JSON
    print(f"💾 Сохранение чанков в файл {self.output_file}...")
    serialized_chunks = [chunk.model_dump() for chunk in all_chunks]

    with open(self.output_file, "w", encoding="utf-8") as f:
      json.dump(serialized_chunks, f, ensure_ascii=False, indent=4)

    print(
        "✅ Чанкинг успешно завершен! Теперь у тебя есть готовый файл с"
        " данными."
    )


if __name__ == "__main__":
  chunker = DataChunker()
  chunker.process_all()
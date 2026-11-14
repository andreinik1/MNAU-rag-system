import json
from pathlib import Path
from app.core.config import settings
from app.services.parser import AdvancedDocumentParser, DocumentChunk


class DataChunker:
    """Утилита для массовой первичной нарезки всех исходных данных."""

    def __init__(
        self,
        raw_data_dir: Path | str = settings.RAW_DIR,
        output_file: Path | str = settings.CHUNKS_FILE,
    ):
        self.raw_dir = Path(raw_data_dir)
        self.texts_dir = self.raw_dir / "texts"
        self.docs_dir = self.raw_dir / "documents"

        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        self.parser = AdvancedDocumentParser()

    def process_all(self):
        """Проходит по всем сырым текстам и документам, режет их на чанки и сохраняет."""
        all_chunks: list[DocumentChunk] = []

        # 1. JSON-страницы из texts/
        if self.texts_dir.exists():
            json_files = list(self.texts_dir.glob("*.json"))
            print(f"📄 Знайдено JSON-сторінок для чанкінгу: {len(json_files)}")

            for i, file_path in enumerate(json_files, 1):
                chunks = self.parser.process_file(str(file_path), category="web_page")
                all_chunks.extend(chunks)
                if i % 100 == 0:
                    print(f"Оброблено веб-сторінок: {i}/{len(json_files)}")

        # 2. Документы из documents/
        if self.docs_dir.exists():
            doc_files = [
                f
                for f in self.docs_dir.iterdir()
                if f.is_file() and not f.name.startswith(".")
            ]
            print(f"📁 Знайдено документів для чанкінгу: {len(doc_files)}")

            for file_path in doc_files:
                chunks = self.parser.process_file(str(file_path))
                all_chunks.extend(chunks)

        print(f"\n🎉 Всього сформовано чанків: {len(all_chunks)}")

        print(f"💾 Збереження чанків у файл {self.output_file}...")
        serialized_chunks = [chunk.model_dump() for chunk in all_chunks]

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(serialized_chunks, f, ensure_ascii=False, indent=2)

        print("✅ Чанкінг успішно завершено!")


if __name__ == "__main__":
    chunker = DataChunker()
    chunker.process_all()

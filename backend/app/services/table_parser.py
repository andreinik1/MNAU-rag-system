import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pdfplumber

from app.models.schemas import DocumentChunk

DAYS_ORDER = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота"]
DAYS_MAP = {
    "понеділок": "Понеділок",
    "вівторок": "Вівторок",
    "середа": "Середа",
    "четвер": "Четвер",
    "п`ятниця": "П'ятниця",
    "п'ятниця": "П'ятниця",
    "пятниця": "П'ятниця",
    "субота": "Субота",
}


def normalize_day(text: Optional[str]) -> Optional[str]:
    """
    Распознает день недели в любом написании:
    прямом ('Понеділок'), вертикальном/обратном ('КОЛІДЕНОП'), с переносами или пробелами.
    """
    if not text:
        return None
    clean = re.sub(r"[\s\n\r_]+", "", text).lower()
    # Прямая проверка
    for k, v in DAYS_MAP.items():
        if k in clean:
            return v
    # Обратная проверка (для вертикального текста снизу вверх в PDF)
    rev = clean[::-1]
    for k, v in DAYS_MAP.items():
        if k in rev:
            return v
    return None


def clean_cell_text(text: Optional[str]) -> str:
    """Очищает текст внутри ячейки таблицы от лишних переводов строк и мусора."""
    if not text:
        return ""
    lines = [line.strip() for line in str(text).split("\n") if line.strip()]
    return " ".join(lines)


def format_table_to_markdown(table: List[List[Optional[str]]]) -> str:
    """Конвертирует двумерный массив ячеек pdfplumber в читаемую Markdown-таблицу."""
    if not table:
        return ""

    cleaned_rows: List[List[str]] = []
    for row in table:
        cleaned_row = [clean_cell_text(cell) for cell in row]
        # Пропускаем полностью пустые строки
        if any(cleaned_row):
            cleaned_rows.append(cleaned_row)

    if not cleaned_rows:
        return ""

    num_cols = max(len(r) for r in cleaned_rows)
    normalized = [r + [""] * (num_cols - len(r)) for r in cleaned_rows]

    header = normalized[0]
    separator = ["---"] * num_cols
    body = normalized[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def is_schedule_content(
    text: str, filename: str = "", table: Optional[List[List[Optional[str]]]] = None
) -> bool:
    """
    Интеллектуальное определение: является ли контент расписанием занятий.
    Проверяет имя файла, наличие дней недели, номеров пар и ключевых слов.
    """
    fn_lower = filename.lower()
    schedule_keywords = ["розклад", "розпис", "schedule", "kurs", "курс", "para", "пари"]
    if any(k in fn_lower for k in schedule_keywords):
        return True

    text_lower = text.lower()
    days_found = sum(1 for d in ["понеділок", "вівторок", "середа", "четвер", "пятниц", "п'ятниц"] if d in text_lower)
    if days_found >= 3:
        return True

    if table and len(table) >= 3:
        all_cells = " ".join(
            [clean_cell_text(c).lower() for r in table[:15] for c in r if c]
        )
        t_days = sum(1 for d in DAYS_MAP.keys() if d in all_cells or d in all_cells[::-1])
        has_pairs = any(f" {i} " in f" {all_cells} " or str(i) in all_cells for i in [1, 2, 3, 4, 5])
        if t_days >= 2 and has_pairs:
            return True

    return False


class ScheduleParser:
    """Специализированный парсер расписаний занятий университета."""

    @classmethod
    def extract_records(cls, pdf_path: Path | str) -> List[Dict[str, Any]]:
        """
        Извлекает гранулярные записи пар из PDF расписания:
        (день, номер пары, специальность, академическая группа, предмет, преподаватель, аудитория).
        """
        records: List[Dict[str, Any]] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    if len(table) < 3:
                        continue

                    num_cols = max(len(r) for r in table)
                    row0 = table[0]
                    row1 = table[1]

                    # 1. Поиск колонки номеров пар
                    pair_col_idx = None
                    for c in range(num_cols):
                        col_vals = [
                            table[r][c].strip()
                            for r in range(2, min(15, len(table)))
                            if table[r] and c < len(table[r]) and table[r][c]
                        ]
                        digits = sum(
                            1 for v in col_vals if v in ["1", "2", "3", "4", "5", "6"]
                        )
                        if digits >= 2:
                            pair_col_idx = c
                            break

                    # 2. Поиск колонки дней недели
                    day_col_idx = None
                    for c in range(num_cols):
                        if c == pair_col_idx:
                            continue
                        col_vals = [
                            table[r][c]
                            for r in range(2, len(table))
                            if table[r] and c < len(table[r]) and table[r][c]
                        ]
                        days = sum(1 for v in col_vals if normalize_day(v) is not None)
                        if days >= 1:
                            day_col_idx = c
                            break

                    # Эвристика по умолчанию, если день не определен явно
                    if day_col_idx is None:
                        if pair_col_idx == 1:
                            day_col_idx = 0
                        elif pair_col_idx == 5 and num_cols > 6:
                            day_col_idx = 6

                    # 3. Построение карты групп: col_idx -> {speciality, group}
                    group_map: Dict[int, Dict[str, str]] = {}
                    current_spec = ""

                    for c in range(num_cols):
                        if c in (day_col_idx, pair_col_idx):
                            continue

                        spec_raw = row0[c] if c < len(row0) and row0[c] else ""
                        if spec_raw and spec_raw.strip():
                            current_spec = clean_cell_text(spec_raw)

                        grp_raw = row1[c] if c < len(row1) and row1[c] else ""
                        grp_clean = clean_cell_text(grp_raw)

                        if not grp_clean and spec_raw and any(ch.isalnum() for ch in spec_raw):
                            grp_clean = clean_cell_text(spec_raw)

                        if grp_clean:
                            group_map[c] = {
                                "speciality": current_spec or "Загальна",
                                "group": grp_clean,
                            }

                    # 4. Проход по строкам пар
                    current_day = "Понеділок"
                    current_pair = "1"

                    for r in range(2, len(table)):
                        row = table[r]
                        if not row:
                            continue

                        # Обновляем день недели
                        if day_col_idx is not None and day_col_idx < len(row):
                            d_val = normalize_day(row[day_col_idx])
                            if d_val:
                                current_day = d_val

                        # Обновляем номер пары
                        if pair_col_idx is not None and pair_col_idx < len(row):
                            p_val = row[pair_col_idx]
                            if p_val and p_val.strip() in ["1", "2", "3", "4", "5", "6"]:
                                current_pair = p_val.strip()

                        # Считываем ячейки для групп с поддержкой merged cells (None)
                        last_valid_content = None
                        last_valid_spec = None

                        for c in range(num_cols):
                            if c in (day_col_idx, pair_col_idx) or c not in group_map:
                                last_valid_content = None
                                continue

                            grp_info = group_map[c]
                            cell_val = row[c] if c < len(row) else None

                            if cell_val is not None:
                                content = clean_cell_text(cell_val)
                                if content:
                                    last_valid_content = content
                                    last_valid_spec = grp_info["speciality"]
                                    records.append({
                                        "page": page_idx,
                                        "day": current_day,
                                        "pair": current_pair,
                                        "speciality": grp_info["speciality"],
                                        "group": grp_info["group"],
                                        "lesson": content,
                                    })
                                else:
                                    last_valid_content = None
                            elif last_valid_content and grp_info["speciality"] == last_valid_spec:
                                # Горизонтально объединенная лекция потока
                                records.append({
                                    "page": page_idx,
                                    "day": current_day,
                                    "pair": current_pair,
                                    "speciality": grp_info["speciality"],
                                    "group": grp_info["group"],
                                    "lesson": last_valid_content,
                                })

        return records

    @classmethod
    def generate_chunks(
        cls,
        pdf_path: Path | str,
        document_title: str = "",
        source_url: str = "",
    ) -> List[DocumentChunk]:
        """
        Генерирует специализированные чанки расписания:
        - Карточка на неделю для каждой академической группы
        - Сводная матрица пар по дням недели
        """
        records = cls.extract_records(pdf_path)
        if not records:
            return []

        title = document_title or Path(pdf_path).name
        chunks: List[DocumentChunk] = []

        # 1. Погрупповые карточки
        groups_dict: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            grp = rec["group"]
            if grp not in groups_dict:
                groups_dict[grp] = {
                    "speciality": rec["speciality"],
                    "days": {d: {} for d in DAYS_ORDER},
                }

            day = rec["day"]
            pair = rec["pair"]
            if day not in groups_dict[grp]["days"]:
                groups_dict[grp]["days"][day] = {}

            existing = groups_dict[grp]["days"][day].get(pair)
            if existing:
                if rec["lesson"] not in existing:
                    groups_dict[grp]["days"][day][pair] = f"{existing} / {rec['lesson']}"
            else:
                groups_dict[grp]["days"][day][pair] = rec["lesson"]

        for grp, info in groups_dict.items():
            spec = info["speciality"]
            lines = [
                f"# РОЗКЛАД ЗАНЯТЬ: {title}",
                f"**Академічна група:** {grp}",
                f"**Спеціальність / Напрям:** {spec}",
                "",
            ]

            for day in DAYS_ORDER:
                pairs_dict = info["days"].get(day, {})
                lines.append(f"### {day}")
                has_pairs = False
                for p in ["1", "2", "3", "4", "5"]:
                    if p in pairs_dict:
                        lines.append(f"- **Пара {p}:** {pairs_dict[p]}")
                        has_pairs = True
                if not has_pairs:
                    lines.append("- *Пар немає (вікно / самопідготовка)*")
                lines.append("")

            card_text = "\n".join(lines).strip()
            chunk_id = hashlib.md5(f"{pdf_path}_group_{grp}".encode("utf-8")).hexdigest()

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_title=f"Розклад групи {grp} ({spec})",
                    text=card_text,
                    metadata={
                        "category": "schedule",
                        "faculty": "all",
                        "group": grp,
                        "speciality": spec,
                        "source_file": title,
                        "source_url": source_url or "",
                    },
                )
            )

        # 2. Сводные таблицы по дням недели
        for day in DAYS_ORDER:
            day_records = [r for r in records if r["day"] == day]
            if not day_records:
                continue

            day_lines = [
                f"# РОЗКЛАД ЗАНЯТЬ: {title} — {day.upper()}",
                f"Зведена таблиця розкладу на {day} для всіх академічних груп:",
                "",
                "| Пара | Група | Спеціальність | Дисципліна, викладач, аудиторія |",
                "| :---: | :--- | :--- | :--- |",
            ]

            day_records.sort(key=lambda x: (x["pair"], x["group"]))
            for r in day_records:
                day_lines.append(
                    f"| Пара {r['pair']} | **{r['group']}** | {r['speciality']} | {r['lesson']} |"
                )

            day_table_text = "\n".join(day_lines)
            chunk_id = hashlib.md5(f"{pdf_path}_day_{day}".encode("utf-8")).hexdigest()

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_title=f"Розклад на {day} ({title})",
                    text=day_table_text,
                    metadata={
                        "category": "schedule",
                        "faculty": "all",
                        "day": day,
                        "source_file": title,
                        "source_url": source_url or "",
                    },
                )
            )

        return chunks


class PDFTableExtractor:
    """Универсальное извлечение таблиц и текста из PDF с помощью pdfplumber."""

    @classmethod
    def extract_tables_and_text(cls, pdf_path: Path | str) -> str:
        """
        Извлекает текст со страниц PDF, аккуратно преобразуя каждую найденную таблицу в Markdown,
        а окружающий текст сохраняя в исходном форматировании.
        """
        output_blocks = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages, 1):
                    tables = page.extract_tables()

                    if tables:
                        output_blocks.append(f"\n--- Сторінка {page_idx} ---\n")
                        # Если на странице есть таблицы, конвертируем их в Markdown
                        for t_idx, table in enumerate(tables, 1):
                            md_table = format_table_to_markdown(table)
                            if md_table:
                                output_blocks.append(f"\n### Таблиця {t_idx} (Сторінка {page_idx}):\n{md_table}\n")

                        # Также добираем текст вне таблиц для полноты контекста
                        raw_page_text = page.extract_text(layout=False) or ""
                        # Очищаем короткие дубли
                        if raw_page_text and len(raw_page_text.strip()) > 50:
                            output_blocks.append(f"\n#### Текстовий опис (Сторінка {page_idx}):\n{raw_page_text.strip()}\n")
                    else:
                        # Обычная текстовая страница без таблиц
                        page_text = page.extract_text(layout=True)
                        if page_text and page_text.strip():
                            output_blocks.append(f"\n--- Сторінка {page_idx} ---\n{page_text.strip()}")

        except Exception as e:
            print(f"❌ Помилка обробки PDF таблиць {pdf_path}: {e}")

        return "\n".join(output_blocks)

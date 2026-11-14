import json
import re
from urllib.parse import urlparse

def is_valid_url(url):
    # 1. Проверка на незакодированные пробелы
    if ' ' in url:
        return False
    
    # 2. Проверка на символы поврежденной кодировки (\ufffd)
    if '\ufffd' in url:
        return False
    
    try:
        parsed = urlparse(url)
        # Проверяем наличие базовой схемы и домена
        if not parsed.scheme or not parsed.netloc:
            return False
        
        path = parsed.path
        
        # 3. Проверка на вложенные протоколы внутри пути (двойные URL)
        if 'http://' in path or 'https://' in path or 'http:/' in path or 'https:/' in path:
            return False
            
        # 4. Проверка на вложенные сторонние домены внутри путей
        external_sub_pattern = r'/(www\.(?!mnau\.edu\.ua)[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
        if re.search(external_sub_pattern, path):
            return False

        # 5. Проверка на дублирование доменов в виде слагов
        if 'https-www' in path or 'http-www' in path:
            return False

        # 6. Проверка на некорректные окончания и спецсимволы
        if path.endswith('\\') or url.endswith('‎'):
            return False

        return True
    except Exception:
        return False

def clean_links(input_file, output_file):
    # Загружаем исходный JSON-файл
    with open(input_file, 'r', encoding='utf-8') as f:
        links = json.load(f)
    
    cleaned_links = []
    trash_links = []
    
    # Распределяем ссылки по спискам
    for link in links:
        if is_valid_url(link):
            cleaned_links.append(link)
        else:
        
            trash_links.append(link)
    
    # Выводим общую статистику
    print(f"Исходное количество ссылок: {len(links)}")
    print(f"Удалено мусорных ссылок: {len(trash_links)}")
    print(f"Итоговое количество корректных ссылок: {len(cleaned_links)}")
    
    # Выводим массив мусорных ссылок в терминал
    print("\n" + "="*40)
    print("СПИСОК УДАЛЕННЫХ МУСОРНЫХ ССЫЛОК:")
    print("="*40)
    for index, trash_url in enumerate(trash_links, start=1):
        print(f"{index}. {trash_url}")
    print("="*40 + "\n")
    
    # Сохраняем очищенные данные в новый файл
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_links, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    clean_links('whitelisted_paths.json', 'cleaned_paths.json')
"""
Скрипт для загрузки книг из Open Library API
"""
import sqlite3
import requests
import time
import json

DB_PATH = 'library.db'
OPEN_LIBRARY_API = 'https://openlibrary.org'

def get_db_connection():
    """Получение соединения с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search_open_library(query, limit=100):
    """Поиск книг в Open Library API"""
    url = f"{OPEN_LIBRARY_API}/search.json"
    params = {
        'q': query,
        'limit': limit,
        'fields': 'title,author_name,first_publish_year,subject,isbn,cover_i,key'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        return None

def get_book_details(work_key):
    """Получение подробной информации о книге"""
    url = f"{OPEN_LIBRARY_API}{work_key}.json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Ошибка при получении деталей книги: {e}")
        return None

def save_book_to_db(book_data):
    """Сохранение книги в базу данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверка на дубликаты по названию и автору
    cursor.execute('''
        SELECT id FROM books 
        WHERE title = ? AND author = ?
    ''', (book_data.get('title', ''), book_data.get('author', '')))
    
    if cursor.fetchone():
        conn.close()
        return False
    
    # Получение обложки
    cover_id = book_data.get('cover_i')
    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""
    
    # Формирование URL источника
    source_url = f"{OPEN_LIBRARY_API}{book_data.get('key', '')}"
    
    # Жанры/темы
    subjects = book_data.get('subject', [])
    genre = ', '.join(subjects[:3]) if subjects else 'Не указано'
    
    cursor.execute('''
        INSERT INTO books (title, author, year, genre, description, cover_url, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        book_data.get('title', 'Без названия'),
        ', '.join(book_data.get('author_name', ['Неизвестный автор'])),
        book_data.get('first_publish_year'),
        genre,
        f"Книга из Open Library. Темы: {', '.join(subjects[:5]) if subjects else 'Не указано'}",
        cover_url,
        source_url
    ))
    
    conn.commit()
    conn.close()
    return True

def load_books_from_open_library(queries, books_per_query=50):
    """Загрузка книг из Open Library по списку запросов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверка существования таблицы
    cursor.execute('''
        SELECT name FROM sqlite_master WHERE type='table' AND name='books'
    ''')
    if not cursor.fetchone():
        print("База данных не инициализирована. Запустите app.py сначала.")
        conn.close()
        return
    
    conn.close()
    
    total_loaded = 0
    
    for query in queries:
        print(f"\nПоиск книг по запросу: '{query}'...")
        results = search_open_library(query, limit=books_per_query)
        
        if not results or 'docs' not in results:
            print(f"Не найдено книг по запросу: {query}")
            continue
        
        books = results['docs']
        print(f"Найдено {len(books)} книг")
        
        for i, book in enumerate(books, 1):
            if save_book_to_db(book):
                total_loaded += 1
                print(f"  [{i}/{len(books)}] Загружена: {book.get('title', 'Без названия')}")
            else:
                print(f"  [{i}/{len(books)}] Пропущена (дубликат): {book.get('title', 'Без названия')}")
            
            # Небольшая задержка, чтобы не перегружать API
            time.sleep(0.1)
    
    print(f"\nВсего загружено новых книг: {total_loaded}")

if __name__ == '__main__':
    # Примеры запросов для загрузки книг
    # Можно изменить на любые интересующие темы
    queries = [
        'python programming',
        'russian literature',
        'classic literature',
        'mathematics',
        'history',
        'science fiction',
        'philosophy',
        'art',
        'biology',
        'physics'
    ]
    
    print("Начало загрузки книг из Open Library...")
    print(f"Запросов: {len(queries)}, книг на запрос: 50")
    print("Это может занять некоторое время...\n")
    
    load_books_from_open_library(queries, books_per_query=50)
    
    print("\nЗагрузка завершена!")


from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
import requests
import time
import hashlib
from bs4 import BeautifulSoup
import re
import smtplib
import ssl
import secrets
from email.mime.text import MIMEText

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
BACKEND_DIR = Path(__file__).parent

app = Flask(__name__,
            template_folder=str(TEMPLATES_DIR),
            static_folder=str(STATIC_DIR))
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24)
CORS(app, supports_credentials=True)

DB_PATH = str(BACKEND_DIR / 'library.db')

MAIL_RU_DOMAINS = frozenset({
    'mail.ru', 'inbox.ru', 'list.ru', 'bk.ru', 'internet.ru', 'mail.ua',
})

_EMAIL_CODES: dict = {}

_CACHE: dict = {}

def cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    value, exp = item
    if exp and exp < time.time():
        _CACHE.pop(key, None)
        return None
    return value

def cache_set(key: str, value, ttl_seconds: int = 120):
    _CACHE[key] = (value, time.time() + ttl_seconds if ttl_seconds else None)


def is_mail_ru_email(email: str) -> bool:
    email = (email or '').strip().lower()
    if '@' not in email:
        return False
    domain = email.rsplit('@', 1)[-1]
    return domain in MAIL_RU_DOMAINS


def verify_mail_ru_mailbox_exists(email: str) -> tuple:
    """Проверка ящика через RCPT TO на MX Mail.ru (при недоступности порта 25 — SKIP_MAILRU_RCPT)."""
    email = (email or '').strip().lower()
    if not is_mail_ru_email(email):
        return False, 'Регистрация только с адреса Mail.ru: mail.ru, inbox.ru, bk.ru, list.ru, internet.ru, mail.ua.'
    local, _, _ = email.partition('@')
    if len(local) < 3 or len(local) > 32:
        return False, 'Некорректная длина имени ящика (от 3 до 32 символов).'
    if not re.match(r'^[a-z0-9._-]+$', local):
        return False, 'Имя ящика: латиница, цифры и символы . _ -'

    if os.environ.get('SKIP_MAILRU_RCPT', '').lower() in ('1', 'true', 'yes'):
        return True, ''

    try:
        with smtplib.SMTP('mxs.mail.ru', 25, timeout=15) as smtp:
            smtp.ehlo('library-catalog.local')
            smtp.mail('')
            code, message = smtp.rcpt(email)
            if code in (250, 251):
                return True, ''
            if code >= 400:
                return False, 'Такого почтового ящика на Mail.ru не найдено или адрес отклонён сервером.'
    except (OSError, smtplib.SMTPException):
        return False, (
            'Не удалось проверить ящик через сервер Mail.ru (часто блокируют порт 25). '
            'Для локальной разработки задайте SKIP_MAILRU_RCPT=1.'
        )
    return True, ''


def send_plain_email(to_addr: str, subject: str, body: str) -> bool:
    host = os.environ.get('SMTP_HOST', 'smtp.mail.ru')
    port = int(os.environ.get('SMTP_PORT', '465'))
    user = os.environ.get('SMTP_USER', '').strip()
    password = os.environ.get('SMTP_PASSWORD', '')
    from_addr = os.environ.get('SMTP_FROM', user).strip() or user
    if not user or not password:
        print(f'[email] SMTP не настроен. Кому: {to_addr}\nТема: {subject}\n{body}')
        return False
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except (OSError, smtplib.SMTPException) as e:
        print(f'[email] ошибка отправки: {e}')
        return False


def migrate_db(conn):
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(users)')
    cols = {row[1] for row in cur.fetchall()}
    if 'email_verified' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0')
    if 'is_blocked' not in cols:
        cur.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0')
    cur.execute('CREATE TABLE IF NOT EXISTS app_migrations (name TEXT PRIMARY KEY)')
    cur.execute("SELECT 1 FROM app_migrations WHERE name = 'purge_non_admin_users_v1'")
    if not cur.fetchone():
        cur.execute('DELETE FROM favorites')
        cur.execute('DELETE FROM users WHERE COALESCE(is_admin, 0) = 0')
        cur.execute("INSERT INTO app_migrations (name) VALUES ('purge_non_admin_users_v1')")


def init_db():
    """Инициализация базы данных с поддержкой полнотекстового поиска"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Создание таблицы книг
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            year INTEGER,
            genre TEXT,
            description TEXT,
            cover_url TEXT,
            file_path TEXT,
            full_text TEXT,
            source_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            email_verified INTEGER NOT NULL DEFAULT 0,
            is_blocked INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создание таблицы избранного
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_title TEXT NOT NULL,
            book_author TEXT,
            book_cover_url TEXT,
            book_source_url TEXT,
            book_year INTEGER,
            book_genre TEXT,
            status TEXT DEFAULT 'favorite',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, book_title, book_author)
        )
    ''')
    
    # Создание индексов для избранного
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_status ON favorites(status)')
    
    # Создание индексов для полнотекстового поиска
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_title ON books(title)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_author ON books(author)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_genre ON books(genre)
    ''')
    
    # Создание виртуальной таблицы для полнотекстового поиска (FTS5)
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
            title, author, genre, description, full_text,
            content='books',
            content_rowid='id'
        )
    ''')
    
    # Создание триггеров для синхронизации FTS5
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
            INSERT INTO books_fts(rowid, title, author, genre, description, full_text)
            VALUES (new.id, new.title, new.author, new.genre, new.description, new.full_text);
        END
    ''')
    
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
            INSERT INTO books_fts(books_fts, rowid, title, author, genre, description, full_text)
            VALUES('delete', old.id, old.title, old.author, old.genre, old.description, old.full_text);
        END
    ''')
    
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
            INSERT INTO books_fts(books_fts, rowid, title, author, genre, description, full_text)
            VALUES('delete', old.id, old.title, old.author, old.genre, old.description, old.full_text);
            INSERT INTO books_fts(rowid, title, author, genre, description, full_text)
            VALUES (new.id, new.title, new.author, new.genre, new.description, new.full_text);
        END
    ''')
    
    migrate_db(conn)
    conn.commit()
    conn.close()

def get_db_connection():
    """Получение соединения с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.before_request
def require_non_blocked_user():
    if not request.path.startswith('/api/'):
        return
    if request.method == 'OPTIONS':
        return
    uid = session.get('user_id')
    if not uid or session.get('is_admin'):
        return
    ep = request.endpoint or ''
    if ep in ('register', 'login', 'logout'):
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT is_blocked FROM users WHERE id = ?', (uid,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['is_blocked']:
        return
    session.clear()
    return jsonify({'error': 'Аккаунт заблокирован'}), 403


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/register')
def register_page():
    """Страница регистрации"""
    return render_template('register.html')

@app.route('/profile')
def profile_page():
    """Страница профиля пользователя"""
    return render_template('profile.html')

@app.route('/admin')
def admin_page():
    """Страница администратора"""
    return render_template('admin.html')

@app.route('/api/books', methods=['GET'])
def get_books():
    """Получение списка всех книг с пагинацией"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    genre = request.args.get('genre', '').strip()
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Общее количество книг (с учетом фильтра жанра)
    if genre:
        cursor.execute('SELECT COUNT(*) as total FROM books WHERE genre = ?', (genre,))
    else:
        cursor.execute('SELECT COUNT(*) as total FROM books')
    total = cursor.fetchone()['total']
    
    # Получение книг с пагинацией
    if genre:
        cursor.execute('''
            SELECT id, title, author, year, genre, description, cover_url, source_url
            FROM books
            WHERE genre = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (genre, per_page, offset))
    else:
        cursor.execute('''
            SELECT id, title, author, year, genre, description, cover_url, source_url
            FROM books
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset))
    
    books = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'books': books,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })

@app.route('/api/search', methods=['GET'])
def search_books():
    """Полнотекстовый поиск книг"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    genre = request.args.get('genre', '')
    year_from = request.args.get('year_from', type=int)
    year_to = request.args.get('year_to', type=int)
    
    offset = (page - 1) * per_page
    
    if not query:
        return jsonify({'books': [], 'total': 0, 'page': page, 'per_page': per_page})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Построение SQL запроса для полнотекстового поиска
    sql = '''
        SELECT b.id, b.title, b.author, b.year, b.genre, b.description, b.cover_url, b.source_url,
               bm.rank
        FROM books b
        JOIN (
            SELECT rowid, rank
            FROM books_fts
            WHERE books_fts MATCH ?
        ) bm ON b.id = bm.rowid
        WHERE 1=1
    '''
    
    params = [f'"{query}" OR {query}*']
    
    # Добавление фильтров
    if genre:
        sql += ' AND b.genre = ?'
        params.append(genre)
    
    if year_from:
        sql += ' AND b.year >= ?'
        params.append(year_from)
    
    if year_to:
        sql += ' AND b.year <= ?'
        params.append(year_to)
    
    sql += ' ORDER BY bm.rank LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    # Выполнение поиска
    try:
        cursor.execute(sql, params)
        books = [dict(row) for row in cursor.fetchall()]
        
        # Подсчет общего количества результатов
        count_sql = sql.replace('SELECT b.id, b.title', 'SELECT COUNT(*) as total').replace('ORDER BY bm.rank LIMIT ? OFFSET ?', '')
        count_params = params[:-2]  # Убираем LIMIT и OFFSET
        cursor.execute(count_sql, count_params)
        total = cursor.fetchone()['total']
    except sqlite3.OperationalError as e:
        # Если FTS5 не поддерживается, используем обычный LIKE поиск
        sql = '''
            SELECT id, title, author, year, genre, description, cover_url, source_url
            FROM books
            WHERE (title LIKE ? OR author LIKE ? OR description LIKE ? OR genre LIKE ?)
        '''
        search_pattern = f'%{query}%'
        params = [search_pattern] * 4
        
        if genre:
            sql += ' AND genre = ?'
            params.append(genre)
        
        if year_from:
            sql += ' AND year >= ?'
            params.append(year_from)
        
        if year_to:
            sql += ' AND year <= ?'
            params.append(year_to)
        
        sql += ' LIMIT ? OFFSET ?'
        params.extend([per_page, offset])
        
        cursor.execute(sql, params)
        books = [dict(row) for row in cursor.fetchall()]
        
        count_sql = sql.replace('SELECT id, title', 'SELECT COUNT(*) as total').replace('LIMIT ? OFFSET ?', '')
        cursor.execute(count_sql, params[:-2])
        total = cursor.fetchone()['total']
    
    conn.close()
    
    return jsonify({
        'books': books,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 0
    })

@app.route('/api/books/<int:book_id>', methods=['GET'])
def get_book(book_id):
    """Получение подробной информации о книге"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM books WHERE id = ?
    ''', (book_id,))
    
    book = cursor.fetchone()
    conn.close()
    
    if book:
        return jsonify(dict(book))
    return jsonify({'error': 'Book not found'}), 404

@app.route('/api/genres', methods=['GET'])
def get_genres():
    """Получение списка всех жанров"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL ORDER BY genre')
    genres = [row['genre'] for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'genres': genres})


@app.route('/api/gutendex/search', methods=['GET'])
def gutendex_search():
    """Поиск через Gutendex (Project Gutenberg) и маппинг под формат фронтенда"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    genre = request.args.get('genre', '').strip()
    # У Gutendex нет явного года публикации; пропустим фильтры годов

    if not query:
        return jsonify({'books': [], 'total': 0, 'page': page, 'per_page': per_page, 'pages': 0})

    # Запросим первую страницу с достаточным лимитом (Gutendex per_page фиксированный ~32)
    try:
        g_params = {'search': query}
        cache_key = f"gu:{json.dumps(g_params, sort_keys=True)}"
        cached = cache_get(cache_key)
        if cached is not None:
            data = cached
        else:
            resp = requests.get('https://gutendex.com/books', params=g_params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            cache_set(cache_key, data, ttl_seconds=300)
        results = data.get('results', [])

        books = []
        for r in results:
            title = r.get('title') or ''
            authors = r.get('authors') or []
            author_names = [a.get('name') for a in authors if isinstance(a, dict) and a.get('name')]
            subjects = r.get('subjects') or []
            formats = r.get('formats') or {}
            cover = formats.get('image/jpeg') or ''
            source_url = r.get('url') or ''

            b = {
                'id': None,
                'title': title,
                'author': ', '.join(author_names) if author_names else '',
                'year': None,
                'genre': ', '.join(subjects[:3]) if subjects else '',
                'description': '',
                'cover_url': cover,
                'source_url': source_url
            }
            if genre:
                if genre.lower() not in b['genre'].lower():
                    continue
            books.append(b)

        total = len(books)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        start = (page - 1) * per_page
        end = start + per_page
        page_items = books[start:end]

        return jsonify({'books': page_items, 'total': total, 'page': page, 'per_page': per_page, 'pages': pages})
    except requests.RequestException as e:
        return jsonify({'error': 'Gutendex request failed', 'details': str(e)}), 502

@app.route('/api/books', methods=['POST'])
def add_book():
    """Добавление новой книги"""
    data = request.get_json()
    
    required_fields = ['title', 'author']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO books (title, author, year, genre, description, cover_url, file_path, full_text, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('title'),
        data.get('author'),
        data.get('year'),
        data.get('genre'),
        data.get('description', ''),
        data.get('cover_url', ''),
        data.get('file_path', ''),
        data.get('full_text', ''),
        data.get('source_url', '')
    ))
    
    book_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': book_id, 'message': 'Book added successfully'}), 201

@app.route('/api/openlibrary/search', methods=['GET'])
def openlibrary_search():
    """Поиск в Open Library API и маппинг результатов под формат фронтенда"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    genre = request.args.get('genre', '').strip()
    year_from = request.args.get('year_from', type=int)
    year_to = request.args.get('year_to', type=int)
    if not query:
        return jsonify({'books': [], 'total': 0, 'page': page, 'per_page': per_page, 'pages': 0})

    # Формируем запрос к Open Library Search API
    # Документация: https://openlibrary.org/dev/docs/api/search
    # Улучшенная формулировка запроса для подстановки префиксов в title/author
    def build_query_with_prefixes(q: str) -> str:
        terms = [t for t in q.replace('\u2014', ' ').replace('\u2013', ' ').split() if t]
        parts = []
        # точная фраза как fallback
        if q:
            parts.append(f'"{q}"')
        # для каждого терма добавляем префиксный поиск по title/author
        for t in terms:
            # если терм короткий (2-3 символа), используем префикс; если длиннее, тоже префикс для подслов
            if len(t) >= 2:
                parts.append(f'(title:{t}* OR author:{t}*)')
            else:
                parts.append(f'(title:{t} OR author:{t})')
        # общий fallback по всему тексту
        if terms:
            for t in terms:
                if len(t) >= 2:
                    parts.append(f'{t}*')
        return ' '.join(parts) if parts else q

    q_ol = build_query_with_prefixes(query)

    # Чтобы корректно фильтровать и пагинировать после фильтров,
    # запрашиваем достаточное количество результатов разом (до 100)
    desired_limit = per_page * page
    if desired_limit > 100:
        desired_limit = 100

    params = {
        'q': q_ol or query,
        'page': 1,
        'limit': desired_limit,
        'mode': 'everything',
        'fields': 'key,title,author_name,first_publish_year,subject,cover_i'
    }

    try:
        cache_key = f"ol:{json.dumps(params, sort_keys=True)}"
        cached = cache_get(cache_key)
        if cached is not None:
            data = cached
        else:
            resp = requests.get('https://openlibrary.org/search.json', params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            cache_set(cache_key, data, ttl_seconds=180)

        docs = data.get('docs', [])

        def build_cover_url(cover_i):
            if not cover_i:
                return ''
            return f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"

        books = []
        for d in docs:
            title = d.get('title') or ''
            authors = d.get('author_name') or []
            year = d.get('first_publish_year')
            subjects = d.get('subject') or []
            cover_i = d.get('cover_i')
            work_key = d.get('key') or ''  # например: '/works/OL123W'

            books.append({
                'id': None,
                'title': title,
                'author': ', '.join(authors) if authors else '',
                'year': year,
                'genre': ', '.join(subjects[:3]) if subjects else '',
                'description': '',
                'cover_url': build_cover_url(cover_i),
                'source_url': f"https://openlibrary.org{work_key}" if work_key else ''
            })

        # Применяем фильтры по жанру и годам
        def matches_filters(book):
            if genre:
                # Проверяем наличие жанра в subjects (используем строку genre по подстроке)
                book_genre = book.get('genre', '')
                if genre.lower() not in book_genre.lower():
                    return False
            y = book.get('year')
            if year_from and (not isinstance(y, int) or y < year_from):
                return False
            if year_to and (not isinstance(y, int) or y > year_to):
                return False
            return True

        filtered = [b for b in books if matches_filters(b)]

        total = len(filtered)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        start = (page - 1) * per_page
        end = start + per_page
        page_items = filtered[start:end]

        return jsonify({
            'books': page_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages
        })
    except requests.RequestException as e:
        return jsonify({'error': 'Open Library request failed', 'details': str(e)}), 502

@app.route('/api/openlibrary/top', methods=['GET'])
def openlibrary_top():
    """Возвращает топ популярных книг (тренд недели) — первые 6"""
    limit = request.args.get('limit', 6, type=int)
    if limit <= 0:
        limit = 6
    if limit > 12:
        limit = 12

    try:
        # Документация: https://openlibrary.org/trending
        cache_key = 'ol_top_thisweek'
        cached = cache_get(cache_key)
        data = None
        if cached is not None:
            data = cached
        else:
            resp = requests.get('https://openlibrary.org/trending/thisweek.json', timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Кэшируем только непустые результаты
            if isinstance(data, dict) and data.get('works'):
                cache_set(cache_key, data, ttl_seconds=300)
        works = (data or {}).get('works', [])

        # Если неделя пустая — пробуем тренды месяца
        if not works:
            cache_key_m = 'ol_top_thismonth'
            cached_m = cache_get(cache_key_m)
            data_m = None
            if cached_m is not None:
                data_m = cached_m
            else:
                resp_m = requests.get('https://openlibrary.org/trending/thismonth.json', timeout=10)
                resp_m.raise_for_status()
                data_m = resp_m.json()
                if isinstance(data_m, dict) and data_m.get('works'):
                    cache_set(cache_key_m, data_m, ttl_seconds=300)
            works = (data_m or {}).get('works', [])

        def build_cover_from_work(w):
            # Open Library trending works often have 'cover_i' or 'cover_id', sometimes 'covers' array
            cover_id = w.get('cover_i') or w.get('cover_id')
            if not cover_id:
                covers = w.get('covers')
                if isinstance(covers, list) and covers:
                    cover_id = covers[0]
            if not cover_id:
                return ''
            return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

        books = []
        for w in works[:limit]:
            title = w.get('title') or ''
            authors = w.get('authors') or []
            author_names = [a.get('name') for a in authors if isinstance(a, dict) and a.get('name')]
            year = w.get('first_publish_year') or w.get('first_publish_date')
            subjects = w.get('subject') or w.get('subject_facet') or []
            key = w.get('key') or ''  # '/works/OL...W'

            books.append({
                'id': None,
                'title': title,
                'author': ', '.join(author_names) if author_names else '',
                'year': year if isinstance(year, int) else None,
                'genre': ', '.join(subjects[:3]) if subjects else '',
                'description': '',
                'cover_url': build_cover_from_work(w),
                'source_url': f"https://openlibrary.org{key}" if key else ''
            })

        return jsonify({'books': books, 'total': len(books)})
    except requests.RequestException as e:
        # игнорируем и переходим к локальному фолбэку ниже
        pass

    # Фолбэк: берём последние книги из локальной БД (если внешние пусты или упали)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, author, year, genre, description, cover_url, source_url
        FROM books
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    books = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Если локальная БД пустая, делаем запрос к Open Library с популярными запросами
    if not books:
        try:
            # Популярные запросы для получения книг
            popular_queries = ['fiction', 'novel', 'classic', 'literature', 'best seller']
            all_books = []
            
            for query in popular_queries:
                if len(all_books) >= limit:
                    break
                    
                params = {
                    'q': query,
                    'page': 1,
                    'limit': limit,
                    'mode': 'everything',
                    'fields': 'key,title,author_name,first_publish_year,subject,cover_i'
                }
                
                resp = requests.get('https://openlibrary.org/search.json', params=params, timeout=8)
                if resp.ok:
                    data = resp.json()
                    docs = data.get('docs', [])
                    
                    for d in docs[:limit]:
                        if len(all_books) >= limit:
                            break
                            
                        title = d.get('title') or ''
                        authors = d.get('author_name') or []
                        year = d.get('first_publish_year')
                        subjects = d.get('subject') or []
                        cover_i = d.get('cover_i')
                        work_key = d.get('key') or ''
                        
                        # Проверяем, что книга не дублируется
                        book_key = f"{title}|{', '.join(authors) if authors else ''}"
                        if any(b.get('_key') == book_key for b in all_books):
                            continue
                        
                        cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else ''
                        
                        all_books.append({
                            'id': None,
                            'title': title,
                            'author': ', '.join(authors) if authors else '',
                            'year': year,
                            'genre': ', '.join(subjects[:3]) if subjects else '',
                            'description': '',
                            'cover_url': cover_url,
                            'source_url': f"https://openlibrary.org{work_key}" if work_key else '',
                            '_key': book_key
                        })
            
            # Убираем служебное поле
            for b in all_books:
                b.pop('_key', None)
            
            if all_books:
                return jsonify({'books': all_books[:limit], 'total': len(all_books[:limit])})
        except Exception:
            pass
    
    return jsonify({'books': books, 'total': len(books)})

@app.route('/api/knigafund/search', methods=['GET'])
def knigafund_search():
    """Поиск через knigafund.ru (web archive)"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    if not query:
        return jsonify({'books': [], 'total': 0, 'page': page, 'per_page': per_page, 'pages': 0})
    
    try:
        # Используем web archive для доступа к knigafund.ru
        archive_url = 'https://web.archive.org/web/20170606112524/http://www.knigafund.ru/'
        search_url = f"{archive_url}search"
        
        cache_key = f"kf:{query}:{page}"
        cached = cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)
        
        # Параметры поиска
        params = {'q': query}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = requests.get(search_url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        books = []
        
        # Парсинг результатов (адаптируем под структуру сайта)
        # Ищем элементы с книгами
        book_items = soup.find_all(['div', 'li', 'article'], class_=re.compile(r'book|item|result', re.I))
        
        if not book_items:
            # Альтернативный поиск
            book_items = soup.find_all(['div', 'li'], attrs={'class': lambda x: x and ('title' in str(x).lower() or 'author' in str(x).lower())})
        
        for item in book_items[:per_page * page]:
            title_elem = item.find(['h1', 'h2', 'h3', 'a', 'span'], class_=re.compile(r'title|name', re.I))
            if not title_elem:
                title_elem = item.find('a')
            
            author_elem = item.find(['span', 'div', 'p'], class_=re.compile(r'author|writer', re.I))
            if not author_elem:
                author_elem = item.find(string=re.compile(r'автор|author', re.I))
            
            cover_elem = item.find('img')
            link_elem = item.find('a', href=True)
            
            title = title_elem.get_text(strip=True) if title_elem else ''
            author = author_elem.get_text(strip=True) if author_elem and hasattr(author_elem, 'get_text') else (str(author_elem).strip() if author_elem else '')
            cover_url = cover_elem.get('src', '') if cover_elem else ''
            source_url = ''
            
            if link_elem:
                href = link_elem.get('href', '')
                if href.startswith('http'):
                    source_url = href
                elif href.startswith('/'):
                    source_url = archive_url.rstrip('/') + href
                else:
                    source_url = archive_url + href
            
            if title:
                books.append({
                    'id': None,
                    'title': title,
                    'author': author or 'Неизвестный автор',
                    'year': None,
                    'genre': '',
                    'description': '',
                    'cover_url': cover_url if cover_url.startswith('http') else (archive_url + cover_url.lstrip('/') if cover_url else ''),
                    'source_url': source_url
                })
        
        # Если не нашли через парсинг, создаем базовые результаты
        if not books and query:
            # Fallback: создаем результат на основе запроса
            books.append({
                'id': None,
                'title': query,
                'author': 'Неизвестный автор',
                'year': None,
                'genre': '',
                'description': f'Результат поиска на knigafund.ru по запросу "{query}"',
                'cover_url': '',
                'source_url': search_url
            })
        
        total = len(books)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        start = (page - 1) * per_page
        end = start + per_page
        page_items = books[start:end]
        
        result = {
            'books': page_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages
        }
        
        cache_set(cache_key, result, ttl_seconds=300)
        return jsonify(result)
        
    except requests.RequestException as e:
        return jsonify({'error': 'Knigafund request failed', 'details': str(e)}), 502
    except Exception as e:
        return jsonify({'error': 'Knigafund parsing failed', 'details': str(e)}), 500

# Функции для работы с паролями
def hash_password(password):
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    """Проверка пароля"""
    return hash_password(password) == password_hash

# API для регистрации
@app.route('/api/register', methods=['POST'])
def register():
    """Регистрация нового пользователя"""
    data = request.get_json()
    
    required_fields = ['first_name', 'last_name', 'email', 'password']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not all([first_name, last_name, email, password]):
        return jsonify({'error': 'All fields are required'}), 400
    
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    ok_mail, mail_err = verify_mail_ru_mailbox_exists(email)
    if not ok_mail:
        return jsonify({'error': mail_err}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверка существующего email
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Email already registered'}), 400
    
    # Создание пользователя
    password_hash = hash_password(password)
    cursor.execute('''
        INSERT INTO users (first_name, last_name, email, password_hash, email_verified, is_blocked)
        VALUES (?, ?, ?, ?, 0, 0)
    ''', (first_name, last_name, email, password_hash))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Создание сессии
    session['user_id'] = user_id
    session['user_email'] = email
    session['user_name'] = f"{first_name} {last_name}"
    
    return jsonify({
        'message': 'Registration successful',
        'user': {
            'id': user_id,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'email_verified': False,
        }
    }), 201

# API для входа
@app.route('/api/login', methods=['POST'])
def login():
    """Вход пользователя"""
    data = request.get_json()
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT id, first_name, last_name, email, password_hash, is_admin, is_blocked, email_verified FROM users WHERE email = ?',
        (email,),
    )
    user = cursor.fetchone()
    conn.close()
    
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid email or password'}), 401

    if user['is_blocked']:
        return jsonify({'error': 'Аккаунт заблокирован'}), 403

    session['user_id'] = user['id']
    session['user_email'] = user['email']
    session['user_name'] = f"{user['first_name']} {user['last_name']}"
    session['is_admin'] = bool(user['is_admin'])
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'email': user['email'],
            'is_admin': bool(user['is_admin']),
            'email_verified': bool(user['email_verified']),
        }
    })

# API для выхода
@app.route('/api/logout', methods=['POST'])
def logout():
    """Выход пользователя"""
    session.clear()
    return jsonify({'message': 'Logout successful'})

# API для проверки текущего пользователя
@app.route('/api/user', methods=['GET'])
def get_current_user():
    """Текущий пользователь по сессии."""
    if 'user_id' not in session:
        return jsonify({'user': None})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT id, first_name, last_name, email, is_admin, created_at, email_verified, is_blocked
        FROM users WHERE id = ?
        ''',
        (session['user_id'],),
    )
    user = cursor.fetchone()
    conn.close()

    if not user:
        session.clear()
        return jsonify({'user': None})

    if user['is_blocked'] and not user['is_admin']:
        session.clear()
        return jsonify({'user': None, 'error': 'Аккаунт заблокирован'})

    return jsonify({
        'user': {
            'id': user['id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'email': user['email'],
            'is_admin': bool(user['is_admin']),
            'created_at': user['created_at'],
            'email_verified': bool(user['email_verified']),
        }
    })


@app.route('/api/user/profile', methods=['PATCH'])
def update_user_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json() or {}
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    if not first_name or not last_name:
        return jsonify({'error': 'Имя и фамилия не могут быть пустыми'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET first_name = ?, last_name = ? WHERE id = ?',
        (first_name, last_name, session['user_id']),
    )
    conn.commit()
    conn.close()
    session['user_name'] = f'{first_name} {last_name}'
    return jsonify({'message': 'Профиль обновлён', 'first_name': first_name, 'last_name': last_name})


@app.route('/api/user/request-email-code', methods=['POST'])
def request_email_verification_code():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    uid = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT email, email_verified FROM users WHERE id = ?', (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Пользователь не найден'}), 404
    if row['email_verified']:
        return jsonify({'error': 'Почта уже подтверждена'}), 400

    email = row['email']
    if not is_mail_ru_email(email):
        return jsonify({'error': 'Код отправляется только на адреса Mail.ru'}), 400

    code = f'{secrets.randbelow(10000):04d}'
    _EMAIL_CODES[uid] = {'code': code, 'expires': time.time() + 15 * 60}
    body = f'Код подтверждения почты в каталоге библиотеки: {code}\nКод действителен 15 минут.'
    sent = send_plain_email(email, 'Код подтверждения почты', body)
    if not sent:
        return jsonify({
            'message': 'Код сформирован, но письмо не отправлено (настройте SMTP_USER/SMTP_PASSWORD). См. консоль сервера.',
            'dev_code_logged': True,
        }), 200

    return jsonify({'message': 'Код отправлен на вашу почту'})


@app.route('/api/user/confirm-email-code', methods=['POST'])
def confirm_email_verification_code():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json() or {}
    entered = (data.get('code') or '').strip()
    if not re.match(r'^\d{4}$', entered):
        return jsonify({'error': 'Введите четырёхзначный код'}), 400

    uid = session['user_id']
    rec = _EMAIL_CODES.get(uid)
    if not rec or rec['expires'] < time.time():
        _EMAIL_CODES.pop(uid, None)
        return jsonify({'error': 'Код устарел или не запрашивался. Запросите новый.'}), 400
    if rec['code'] != entered:
        return jsonify({'error': 'Неверный код'}), 400

    _EMAIL_CODES.pop(uid, None)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE users SET email_verified = 1 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Почта подтверждена', 'email_verified': True})

# API для добавления в избранное
@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """Добавление книги в избранное"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    required_fields = ['book_title']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    user_id = session['user_id']
    book_title = data.get('book_title', '').strip()
    book_author = data.get('book_author', '').strip()
    book_cover_url = data.get('book_cover_url', '')
    book_source_url = data.get('book_source_url', '')
    book_year = data.get('book_year')
    book_genre = data.get('book_genre', '')
    status = data.get('status', 'favorite')  # favorite, read, reading, planned, read_complete
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверка на дубликат
    cursor.execute('''
        SELECT id FROM favorites 
        WHERE user_id = ? AND book_title = ? AND book_author = ?
    ''', (user_id, book_title, book_author))
    
    if cursor.fetchone():
        # Обновляем статус, если книга уже есть
        cursor.execute('''
            UPDATE favorites 
            SET status = ?, book_cover_url = ?, book_source_url = ?, book_year = ?, book_genre = ?
            WHERE user_id = ? AND book_title = ? AND book_author = ?
        ''', (status, book_cover_url, book_source_url, book_year, book_genre, user_id, book_title, book_author))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Favorite updated'})
    
    # Добавление новой записи
    cursor.execute('''
        INSERT INTO favorites (user_id, book_title, book_author, book_cover_url, book_source_url, book_year, book_genre, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, book_title, book_author, book_cover_url, book_source_url, book_year, book_genre, status))
    
    favorite_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': favorite_id, 'message': 'Book added to favorites'}), 201

# API для получения избранного
@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    """Получение списка избранных книг пользователя"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_id = session['user_id']
    status = request.args.get('status', '')  # фильтр по статусу
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute('''
            SELECT * FROM favorites 
            WHERE user_id = ? AND status = ?
            ORDER BY created_at DESC
        ''', (user_id, status))
    else:
        cursor.execute('''
            SELECT * FROM favorites 
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
    
    favorites = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'favorites': favorites})

# API для удаления из избранного
@app.route('/api/favorites/<int:favorite_id>', methods=['DELETE'])
def delete_favorite(favorite_id):
    """Удаление книги из избранного"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM favorites WHERE id = ? AND user_id = ?', (favorite_id, user_id))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Favorite not found'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Favorite deleted'})

# API для обновления статуса избранного
@app.route('/api/favorites/<int:favorite_id>/status', methods=['PUT'])
def update_favorite_status(favorite_id):
    """Обновление статуса книги в избранном"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    status = data.get('status', 'favorite')
    
    valid_statuses = ['favorite', 'read', 'reading', 'planned', 'read_complete']
    if status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE favorites 
        SET status = ? 
        WHERE id = ? AND user_id = ?
    ''', (status, favorite_id, user_id))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Favorite not found'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Status updated'})

# Админ API - получение списка пользователей
@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403

    blocked_only = request.args.get('blocked', '').lower() in ('1', 'true', 'yes')

    conn = get_db_connection()
    cursor = conn.cursor()
    if blocked_only:
        cursor.execute(
            '''
            SELECT id, first_name, last_name, email, created_at, is_admin, email_verified, is_blocked
            FROM users
            WHERE is_blocked = 1
            ORDER BY LOWER(last_name), LOWER(first_name), id
            '''
        )
    else:
        cursor.execute(
            '''
            SELECT id, first_name, last_name, email, created_at, is_admin, email_verified, is_blocked
            FROM users
            WHERE is_blocked = 0 OR is_blocked IS NULL
            ORDER BY LOWER(last_name), LOWER(first_name), id
            '''
        )

    users = [dict(row) for row in cursor.fetchall()]
    conn.close()

    for u in users:
        u['is_admin'] = bool(u.get('is_admin'))
        u['email_verified'] = bool(u.get('email_verified'))
        u['is_blocked'] = bool(u.get('is_blocked'))

    return jsonify({'users': users, 'total': len(users)})


@app.route('/api/admin/users/<int:target_id>', methods=['GET'])
def admin_get_user_detail(target_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT id, first_name, last_name, email, created_at, is_admin, email_verified, is_blocked
        FROM users WHERE id = ?
        ''',
        (target_id,),
    )
    user = cur.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Пользователь не найден'}), 404

    cur.execute(
        '''
        SELECT id, book_title, book_author, status, created_at
        FROM favorites WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 200
        ''',
        (target_id,),
    )
    favorites = [dict(r) for r in cur.fetchall()]
    conn.close()

    u = dict(user)
    u['is_admin'] = bool(u.get('is_admin'))
    u['email_verified'] = bool(u.get('email_verified'))
    u['is_blocked'] = bool(u.get('is_blocked'))
    return jsonify({'user': u, 'favorites': favorites})


@app.route('/api/admin/users/<int:target_id>/block', methods=['POST'])
def admin_block_user(target_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403
    if target_id == session['user_id']:
        return jsonify({'error': 'Нельзя заблокировать свою учётную запись'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT is_admin FROM users WHERE id = ?', (target_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    if row['is_admin']:
        conn.close()
        return jsonify({'error': 'Нельзя заблокировать администратора'}), 400

    cur.execute('UPDATE users SET is_blocked = 1 WHERE id = ?', (target_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Пользователь заблокирован'})


@app.route('/api/admin/users/<int:target_id>/unblock', methods=['POST'])
def admin_unblock_user(target_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Admin access required'}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_blocked = 0 WHERE id = ?', (target_id,))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    conn.commit()
    conn.close()
    return jsonify({'message': 'Блокировка снята'})

# Админ API - вход администратора
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Вход администратора"""
    data = request.get_json()
    
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    password = data.get('password', '')
    
    if not all([first_name, last_name, password]):
        return jsonify({'error': 'Все поля обязательны'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Поиск администратора по имени и фамилии (без учета регистра)
    cursor.execute('''
        SELECT id, first_name, last_name, email, password_hash, is_admin, is_blocked
        FROM users 
        WHERE LOWER(TRIM(first_name)) = LOWER(TRIM(?)) 
        AND LOWER(TRIM(last_name)) = LOWER(TRIM(?)) 
        AND is_admin = 1
    ''', (first_name, last_name))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Неверные учетные данные'}), 401

    if user['is_blocked']:
        return jsonify({'error': 'Учётная запись заблокирована'}), 403
    
    session['user_id'] = user['id']
    session['user_email'] = user['email']
    session['user_name'] = f"{user['first_name']} {user['last_name']}"
    session['is_admin'] = True
    
    return jsonify({
        'message': 'Admin login successful',
        'user': {
            'id': user['id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'email': user['email']
        }
    })

# Обновление aggregate search для включения knigafund
@app.route('/api/search/aggregate', methods=['GET'])
def aggregate_search():
    """Агрегированный поиск по Open Library, Gutendex и Knigafund"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    genre = request.args.get('genre', '').strip()
    year_from = request.args.get('year_from', type=int)
    year_to = request.args.get('year_to', type=int)

    if not query:
        return jsonify({'books': [], 'total': 0, 'page': page, 'per_page': per_page, 'pages': 0})

    books_all = []

    def safe_get(url, params):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.ok:
                return r.json()
        except requests.RequestException:
            return None
        return None

    base = (os.environ.get('APP_BASE_URL') or request.url_root).rstrip('/')
    if base and not base.startswith('http'):
        base = f'https://{base}'

    # Open Library (через локальный прокси)
    ol = safe_get(f'{base}/api/openlibrary/search', {
        'q': query, 'page': 1, 'per_page': 40, 'genre': genre, 'year_from': year_from, 'year_to': year_to
    })
    if ol and isinstance(ol.get('books'), list):
        books_all.extend(ol['books'])

    # Gutendex
    gu = safe_get(f'{base}/api/gutendex/search', {
        'q': query, 'page': 1, 'per_page': 40, 'genre': genre
    })
    if gu and isinstance(gu.get('books'), list):
        books_all.extend(gu['books'])

    # Knigafund
    kf = safe_get(f'{base}/api/knigafund/search', {
        'q': query, 'page': 1, 'per_page': 40
    })
    if kf and isinstance(kf.get('books'), list):
        books_all.extend(kf['books'])

    total = len(books_all)
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    start = (page - 1) * per_page
    end = start + per_page
    page_items = books_all[start:end]

    return jsonify({'books': page_items, 'total': total, 'page': page, 'per_page': per_page, 'pages': pages})

if __name__ == '__main__':
    init_db()
    print("База данных инициализирована")
    print("Сервер запущен на http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)


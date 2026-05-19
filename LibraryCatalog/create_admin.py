"""
Создание учётной записи администратора в БД каталога.
Запуск из корня проекта: python create_admin.py
"""
import sys
import os
from pathlib import Path

# Добавляем backend в путь
backend_dir = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_dir))

from app import get_db_connection, hash_password, init_db

def create_admin():
    init_db()
    print("=" * 60)
    print("Создание администратора")
    print("=" * 60)
    
    # Используем предустановленные данные
    first_name = "Юрий"
    last_name = "Андрущенко"
    email = "admin@library.local"
    password = "123123"
    
    print(f"Имя: {first_name}")
    print(f"Фамилия: {last_name}")
    print(f"Email: {email}")
    print(f"Пароль: {password}")
    print("=" * 60)
    
    if not all([first_name, last_name, email, password]):
        print("Ошибка: Все поля обязательны!")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверка существующего администратора с таким email или именем/фамилией
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    existing_by_email = cursor.fetchone()
    
    cursor.execute('SELECT id FROM users WHERE first_name = ? AND last_name = ? AND is_admin = 1', (first_name, last_name))
    existing_by_name = cursor.fetchone()
    
    password_hash = hash_password(password)
    
    if existing_by_email or existing_by_name:
        # Обновляем существующего администратора
        user_id = existing_by_email['id'] if existing_by_email else existing_by_name['id']
        cursor.execute('''
            UPDATE users 
            SET first_name = ?, last_name = ?, email = ?, password_hash = ?, is_admin = 1,
                is_blocked = 0, email_verified = COALESCE(email_verified, 0)
            WHERE id = ?
        ''', (first_name, last_name, email, password_hash, user_id))
        print(f"Обновлен существующий администратор (ID: {user_id})")
    else:
        # Создание нового администратора
        cursor.execute('''
            INSERT INTO users (first_name, last_name, email, password_hash, is_admin, email_verified, is_blocked)
            VALUES (?, ?, ?, ?, 1, 0, 0)
        ''', (first_name, last_name, email, password_hash))
        user_id = cursor.lastrowid
        print(f"Создан новый администратор (ID: {user_id})")
    
    conn.commit()
    conn.close()
    
    print("=" * 60)
    print("Администратор успешно создан!")
    print(f"ID: {user_id}")
    print(f"Имя: {first_name} {last_name}")
    print(f"Email: {email}")
    print("=" * 60)
    print("\nТеперь вы можете войти в административную панель:")
    print("1. Локально: start.bat, затем http://localhost:5000/admin")
    print("2. На хостинге: https://yoori2323.pythonanywhere.com/admin")
    print("3. Войдите используя имя, фамилию и пароль")
    print("=" * 60)

if __name__ == '__main__':
    try:
        create_admin()
    except KeyboardInterrupt:
        print("\n\nОтменено пользователем.")
    except Exception as e:
        print(f"\nОшибка: {e}")



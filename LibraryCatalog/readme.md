# Запуск сайта (локально)

1. Запустите `start.bat`.
2. Дождитесь сообщения о запуске сервера.
3. В браузере откройте: **http://localhost:5000**

При первом запуске скрипт сам установит зависимости из `backend/requirements.txt`.

# Админ-панель

| Где | Адрес |
|-----|--------|
| Локально | http://localhost:5000/admin (через `start.bat`) |
| Хостинг | https://yoori2323.pythonanywhere.com/admin |

Учётные данные администратора задаются в `create_admin.py` (по умолчанию: Юрий Андрущенко / `123123`).

# Хостинг PythonAnywhere

Пошаговая выкладка через GitHub: **[DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md)**

База данных SQLite создаётся автоматически в `backend/library.db` при первом запуске (в Git не попадает).

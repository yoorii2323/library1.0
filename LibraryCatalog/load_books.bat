@echo off
chcp 65001 >nul
echo ========================================
echo Загрузка книг из Open Library API
echo ========================================
echo.
echo ВНИМАНИЕ: Убедитесь, что сервер запущен (app.py)!
echo.
pause

cd backend

echo Поиск Python...
set "PY_CMD="
where py >nul 2>&1 && set "PY_CMD=py"
if not defined PY_CMD (
    where python >nul 2>&1 && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo ОШИБКА: Python не найден в PATH.
    echo Установите Python или добавьте его в PATH.
    pause
    exit /b 1
)
%PY_CMD% --version >nul 2>&1

echo.
echo Начало загрузки книг...
echo Это может занять несколько минут...
echo.

%PY_CMD% load_books.py

echo.
echo Загрузка завершена!
pause


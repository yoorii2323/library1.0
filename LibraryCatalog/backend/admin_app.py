"""
Отдельное приложение для запуска административной панели
"""
from app import app
import os

if __name__ == '__main__':
    print("=" * 60)
    print("Административная панель")
    print("=" * 60)
    print("Откройте в браузере: http://localhost:5001/admin")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5001)



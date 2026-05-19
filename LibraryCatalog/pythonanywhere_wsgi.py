"""
Содержимое для WSGI на PythonAnywhere (Web → Code → WSGI configuration file).

Скопируйте этот файл в редактор WSGI на хостинге или укажите путь к клону репозитория ниже.

После git clone репозитория типичный путь:
  /home/yoori2323/ИМЯ_РЕПОЗИТОРИЯ
Если в корне репозитория лежат папки backend, templates, static — используйте этот путь.
Если репозиторий содержит вложенную папку LibraryCatalog — добавьте /LibraryCatalog.
"""
import sys
import os

# Путь к корню проекта на PythonAnywhere (измените ИМЯ_РЕПО, если клонировали под другим именем)
path_project = '/home/yoori2323/LibraryCatalog'
path_backend = os.path.join(path_project, 'backend')

if path_backend not in sys.path:
    sys.path.insert(0, path_backend)
if path_project not in sys.path:
    sys.path.insert(0, path_project)

os.chdir(path_backend)

from app import app as application  # noqa: E402
from app import init_db  # noqa: E402

init_db()

from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

application = ProxyFix(application, x_for=1, x_proto=1, x_host=1, x_prefix=1)

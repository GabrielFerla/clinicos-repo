"""WSGI config para o projeto ClinicOS.

Expõe a callable WSGI como módulo-level `application`. Usada em produção por
gunicorn/uwsgi. O settings padrão pode ser sobrescrito via env
`DJANGO_SETTINGS_MODULE`.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

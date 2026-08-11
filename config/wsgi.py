"""WSGI config para o projeto ClinicOS.

Expõe a callable WSGI como módulo-level `application`. Usada em produção por
gunicorn/uwsgi. O settings padrão pode ser sobrescrito via env
`DJANGO_SETTINGS_MODULE`.
"""

import os

from django.core.wsgi import get_wsgi_application

# `config.settings` é um **pacote**, e o `__init__.py` dele não reexporta nada
# — subir com ele significaria bootar sem nenhuma configuração. Em produção o
# processo exporta `config.settings.prod`; este default só evita que um
# gunicorn sem env var suba num estado silenciosamente quebrado.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()

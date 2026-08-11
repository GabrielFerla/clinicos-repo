"""ASGI config para o projeto ClinicOS.

Expõe a callable ASGI como módulo-level `application`. Necessária para
Channels/Daphne ou qualquer servidor assíncrono. O settings padrão pode ser
sobrescrito via env `DJANGO_SETTINGS_MODULE`.
"""

import os

from django.core.asgi import get_asgi_application

# Ver a nota em `config/wsgi.py`: `config.settings` é um pacote vazio.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()

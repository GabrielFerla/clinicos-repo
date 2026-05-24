"""ASGI config para o projeto ClinicOS.

Expõe a callable ASGI como módulo-level `application`. Necessária para
Channels/Daphne ou qualquer servidor assíncrono. O settings padrão pode ser
sobrescrito via env `DJANGO_SETTINGS_MODULE`.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

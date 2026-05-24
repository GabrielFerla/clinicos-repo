"""Settings de desenvolvimento local.

Herda tudo de ``base.py`` e sobrescreve apenas o que for específico de dev:

- ``DEBUG = True`` para páginas de erro e auto-reload úteis.
- ``ALLOWED_HOSTS = ["*"]`` para aceitar requests vindas do container Django
  exposto em ``localhost:8000`` (e qualquer hostname interno do compose).
- Email vai para o **Mailhog** via SMTP (host/port já lidos do ambiente em
  ``base.py``). UI de inspeção em http://localhost:8025.

Cadeia de herança: ``base.py`` → ``dev.py``.
Selecione com ``DJANGO_SETTINGS_MODULE=config.settings.dev`` (default em
``manage.py``).
"""

from __future__ import annotations

from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Emails reais via SMTP do Mailhog (host/port vêm do ambiente em base.py).
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# TODO(S1-7): django-debug-toolbar e django-extensions podem entrar aqui
# quando S1-7 configurar django-environ e dependências de dev.

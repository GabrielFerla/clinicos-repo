"""Settings de produção.

Herda tudo de ``base.py`` e endurece a configuração para deploy real.

- ``DEBUG = False`` (default já, mas reafirmado).
- ``ALLOWED_HOSTS`` deve vir de ``DJANGO_ALLOWED_HOSTS`` no ambiente (lida em
  ``base.py``). Se faltar, ``ALLOWED_HOSTS=[]`` e o Django bloqueia tudo —
  comportamento desejado em prod.
- Cookies seguros, HSTS, proteção contra sniffing e cabeçalho de proxy SSL.

Cadeia de herança: ``base.py`` → ``prod.py``.
Selecione com ``DJANGO_SETTINGS_MODULE=config.settings.prod`` no servidor.
"""

from __future__ import annotations

from .base import *  # noqa: F401,F403

DEBUG = False

# Atrás de um proxy/load balancer que termina TLS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies só por HTTPS.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS: começa "leve" (1 dia). Aumentar gradualmente quando o deploy estiver
# estável e o domínio definitivo for confirmado.
SECURE_HSTS_SECONDS = 60 * 60 * 24  # 1 dia
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

# Outros hardenings comuns.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Redireciona HTTP→HTTPS no nível da aplicação (em complemento ao proxy).
SECURE_SSL_REDIRECT = True

# TODO: configurar logging estruturado (JSON) + Sentry/observabilidade quando a
# infra de prod estiver definida.

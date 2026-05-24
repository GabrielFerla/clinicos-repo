"""Settings base do ClinicOS — compartilhado por todos os ambientes.

Este módulo **não** deve ser usado diretamente como ``DJANGO_SETTINGS_MODULE``.
Em vez disso, cada ambiente (``dev``, ``prod``, ``test``) faz::

    from .base import *  # noqa: F403

e sobrescreve apenas o necessário.

Variáveis de ambiente lidas aqui (vide ``docker-compose.yml``):

- ``DJANGO_SECRET_KEY`` (obrigatória — falha rápido se faltar)
- ``DJANGO_ALLOWED_HOSTS`` (CSV; default vazio)
- ``DATABASE_URL`` (preferida) **ou** ``DB_HOST``/``DB_PORT``/``DB_NAME``/
  ``DB_USER``/``DB_PASSWORD`` (fallback)
- ``REDIS_URL`` (cache)
- ``CELERY_BROKER_URL``
- ``EMAIL_HOST`` / ``EMAIL_PORT`` / ``EMAIL_USE_TLS``

S1-7 substituirá ``os.environ`` por ``django-environ`` mantendo as mesmas
chaves. Aqui usamos ``os.environ`` direto para destravar a S1-6 sem criar
dependência cruzada.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Segurança
# ---------------------------------------------------------------------------
# Sem default: se a env var faltar, o Django falha imediatamente — é o que
# queremos em qualquer ambiente real. Para rodar localmente, o
# ``docker-compose.yml`` injeta ``DJANGO_SECRET_KEY=dev-insecure-change-me``.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = False

_allowed_hosts_raw = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS: list[str] = (
    [h.strip() for h in _allowed_hosts_raw.split(",") if h.strip()]
    if _allowed_hosts_raw
    else []
)


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
# Os 6 apps de domínio são criados em S1-5 (paralelo). Estamos só referenciando
# para que o INSTALLED_APPS já fique no formato final esperado pela Sprint 1.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps de domínio do ClinicOS
    "apps.core",
    "apps.agenda",
    "apps.prontuario",
    "apps.chatbot",
    "apps.crm",
    "apps.site_publico",
]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ---------------------------------------------------------------------------
# URL / WSGI / ASGI
# ---------------------------------------------------------------------------
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Banco de dados (Oracle 23ai)
# ---------------------------------------------------------------------------
# Aceita duas formas:
#
# 1. ``DATABASE_URL`` no formato ``oracle://user:password@host:port/?service_name=PDB``
#    (preferida; é o que o docker-compose injeta).
# 2. Variáveis individuais ``DB_HOST``, ``DB_PORT``, ``DB_NAME``, ``DB_USER``,
#    ``DB_PASSWORD`` (fallback útil para ambientes onde a URL é montada por
#    outra ferramenta).
#
# Se nada estiver definido, cai num default explícito apontando para o serviço
# ``oracle`` do compose. Isso evita explosão silenciosa em manage.py check, mas
# *qualquer* operação real vai bater no Oracle.
def _build_database_config() -> dict[str, dict[str, object]]:
    """Monta o ``DATABASES`` lendo env vars (URL preferida, vars individuais como fallback)."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        query = parse_qs(parsed.query)
        service_name = query.get("service_name", ["FREEPDB1"])[0]
        host = parsed.hostname or "oracle"
        port = parsed.port or 1521
        # ``parsed.path`` pode estar vazio quando usamos ?service_name=...; nesse
        # caso o NAME do Django deve ser "host:port/service_name" (formato do
        # driver oracledb thin).
        name = f"{host}:{port}/{service_name}"
        return {
            "default": {
                "ENGINE": "django.db.backends.oracle",
                "NAME": name,
                "USER": parsed.username or "clinicos",
                "PASSWORD": parsed.password or "",
                "HOST": "",  # já embutido em NAME
                "PORT": "",
            }
        }

    # Fallback: variáveis individuais.
    db_host = os.environ.get("DB_HOST", "oracle")
    db_port = os.environ.get("DB_PORT", "1521")
    db_name = os.environ.get("DB_NAME", "FREEPDB1")
    return {
        "default": {
            "ENGINE": "django.db.backends.oracle",
            "NAME": f"{db_host}:{db_port}/{db_name}",
            "USER": os.environ.get("DB_USER", "clinicos"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": "",
            "PORT": "",
        }
    }


DATABASES = _build_database_config()


# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}


# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_HOST = os.environ.get("EMAIL_HOST", "mailhog")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "1025"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "False").lower() in ("true", "1", "yes")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@clinicos.local")


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# TODO(S1-8): o modelo Usuario custom será criado em ``apps.core``. Até lá o
# app ``apps.core`` está vazio e essa referência fará o Django reclamar APENAS
# se algo tentar resolver ``AUTH_USER_MODEL`` (ex.: criar migrations).
# ``manage.py check`` puro não dispara o erro. A S1-8 entrega o model real.
AUTH_USER_MODEL = "core.Usuario"


# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_L10N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Arquivos estáticos e mídia
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS: list[Path] = []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------------------------
# Defaults Django
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

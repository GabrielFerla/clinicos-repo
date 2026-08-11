"""Settings base do ClinicOS — compartilhado por todos os ambientes.

Este módulo **não** deve ser usado diretamente como ``DJANGO_SETTINGS_MODULE``.
Em vez disso, cada ambiente (``dev``, ``prod``, ``test``) faz::

    from .base import *  # noqa: F403

e sobrescreve apenas o necessário.

Variáveis de ambiente lidas aqui (vide ``docker-compose.yml`` e ``.env.example``):

- ``DJANGO_SECRET_KEY`` (obrigatória — falha rápido se faltar)
- ``DJANGO_DEBUG`` (bool, default ``False``)
- ``DJANGO_ALLOWED_HOSTS`` (CSV; default vazio)
- ``DATABASE_URL`` (formato ``oracle://user:password@host:port/?service_name=PDB``)
- ``REDIS_URL`` (cache)
- ``CELERY_BROKER_URL``
- ``CELERY_RESULT_BACKEND`` (default = ``CELERY_BROKER_URL``)
- ``EMAIL_URL`` (preferida) **ou** ``EMAIL_HOST`` / ``EMAIL_PORT`` /
  ``EMAIL_USE_TLS`` / ``EMAIL_HOST_USER`` / ``EMAIL_HOST_PASSWORD``
- ``DEFAULT_FROM_EMAIL``
- ``CPF_ENCRYPTION_KEY`` (placeholder; usado em S1-13)
- ``CPF_HASH_PEPPER`` (placeholder; usado em S1-14)

A leitura é feita via :mod:`environ` (``django-environ``), que cuida do parsing
de URLs (DATABASE_URL, REDIS_URL, EMAIL_URL) e do cast de tipos (bool/list/int).
Se houver um arquivo ``.env`` na raiz do repo, ele é carregado automaticamente
para facilitar execução fora do Docker (ver ``.env.example``).
"""

from __future__ import annotations

from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# django-environ
# ---------------------------------------------------------------------------
# ``env`` é o único ponto de leitura de variáveis de ambiente neste arquivo.
# Cast/default já ficam declarados na chamada — nunca usar ``os.environ`` direto
# aqui pra evitar duas fontes de verdade.
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)

# Carrega ``.env`` se existir (uso típico: dev local rodando ``manage.py`` fora
# do container). Dentro do Docker as variáveis chegam pelo ``environment:`` do
# compose e este ``read_env`` simplesmente não encontra arquivo — no-op seguro.
environ.Env.read_env(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Segurança
# ---------------------------------------------------------------------------
# Sem default: se a env var faltar, o ``django-environ`` levanta
# ``ImproperlyConfigured`` imediatamente — é o que queremos em qualquer ambiente
# real. Para rodar localmente, o ``docker-compose.yml`` injeta
# ``DJANGO_SECRET_KEY=dev-insecure-change-me``.
SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])


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
    # Frontend / tema (django-tailwind — S1-17)
    "tailwind",
    "apps.theme",
    # Apps de domínio do ClinicOS
    "apps.core",
    "apps.agenda",
    "apps.prontuario",
    "apps.chatbot",
    "apps.crm",
    "apps.site_publico",
]


# ---------------------------------------------------------------------------
# Tailwind (django-tailwind — S1-17)
# ---------------------------------------------------------------------------
# ``TAILWIND_APP_NAME`` aponta para o app que hospeda ``static_src/`` (com
# package.json, tailwind.config.js etc.). ``INTERNAL_IPS`` é necessário para
# que o browser-reload do ``django-tailwind[reload]`` funcione no dev.
# ``NPM_BIN_PATH`` indica onde está o binário do npm no container.
TAILWIND_APP_NAME = "apps.theme"
INTERNAL_IPS = ["127.0.0.1"]
NPM_BIN_PATH = "npm"


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
# ``env.db_url`` faz o parsing de ``DATABASE_URL`` no formato
# ``oracle://user:password@host:port/?service_name=PDB`` e devolve o dict no
# formato esperado pelo Django. O default aponta para o serviço ``oracle`` do
# compose, evitando explosão silenciosa em ``manage.py check`` — qualquer
# operação real ainda precisa do Oracle no ar.
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="oracle://clinicos:oracle@oracle:1521/?service_name=FREEPDB1",
    ),
}


# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
# ``env.cache_url`` traduz ``redis://host:port/db`` no dict ``CACHES``
# esperado pelo Django (BACKEND + LOCATION).
CACHES = {
    "default": env.cache_url("REDIS_URL", default="redis://redis:6379/0"),
}


# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Duas formas de configurar email:
#
# 1. ``EMAIL_URL`` — formato ``smtp://user:password@host:port`` (preferida em
#    prod / staging, onde a config muda por ambiente). django-environ
#    converte para EMAIL_HOST / EMAIL_PORT / EMAIL_HOST_USER /
#    EMAIL_HOST_PASSWORD / EMAIL_USE_TLS automaticamente.
# 2. Variáveis individuais ``EMAIL_HOST``/``EMAIL_PORT``/``EMAIL_USE_TLS``/
#    ``EMAIL_HOST_USER``/``EMAIL_HOST_PASSWORD`` — é o que o ``docker-compose``
#    injeta hoje (Mailhog).
if env("EMAIL_URL", default=""):
    vars().update(env.email_url("EMAIL_URL"))
else:
    EMAIL_HOST = env("EMAIL_HOST", default="mailhog")
    EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@clinicos.local")


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


# ---------------------------------------------------------------------------
# Cripto LGPD (placeholders — preenchidos em S1-13/S1-14)
# ---------------------------------------------------------------------------
# Chave AES-256 (urlsafe base64, 32 bytes) usada para criptografar CPF em
# repouso. S1-13 implementa o helper de criptografia. Gere com::
#
#     python -c "import secrets; print(secrets.token_urlsafe(32))"
#
# Em prod, injetar via secret manager. Em dev, definir no ``.env``.
CPF_ENCRYPTION_KEY = env("CPF_ENCRYPTION_KEY", default=None)

# Pepper para hash determinístico HMAC-SHA256 do CPF (busca por igualdade
# sem expor o valor em claro). S1-14 implementa o helper. Mesma origem que
# ``CPF_ENCRYPTION_KEY``: secret manager em prod, ``.env`` em dev.
CPF_HASH_PEPPER = env("CPF_HASH_PEPPER", default=None)


# ---------------------------------------------------------------------------
# Chatbot — LLM e embeddings (Sprint 5)
# ---------------------------------------------------------------------------
# No MVP1 o LLM roda **local, via Ollama**, pelo endpoint compatível com a API
# da OpenAI. O compromisso do projeto com a Anthropic (README, ADR-0002) segue
# de pé — ver ``docs/CHAT_MVP.md``. O código fala com uma interface
# (``apps.chatbot.services.llm.base.LLMClient``), então trocar o provedor é
# mudar ``LLM_PROVIDER``, não reescrever o ``ChatService``.

LLM_PROVIDER = env("LLM_PROVIDER", default="ollama")
LLM_BASE_URL = env("LLM_BASE_URL", default="http://host.docker.internal:11434/v1")
# O cliente OpenAI recusa api_key vazia; o Ollama ignora o valor.
LLM_API_KEY = env("LLM_API_KEY", default="ollama")

# IMPORTANTE: use um modelo **sem "thinking"**. Modelos da família qwen3
# raciocinam antes de responder e não há como desligar isso pela API (medido:
# `think:false`, `enable_thinking` e `/no_think` são todos ignorados ou fazem
# o raciocínio vazar como resposta). Na prática isso vira de 8 a 45 segundos
# de tela em branco. Ver docs/CHAT_MVP.md §4.2.
LLM_MODEL = env("LLM_MODEL", default="qwen2.5:3b")
LLM_TEMPERATURE = env.float("LLM_TEMPERATURE", default=0.1)
LLM_TIMEOUT_SEGUNDOS = env.int("LLM_TIMEOUT_SEGUNDOS", default=120)
# Quantas rodadas de tool call são permitidas antes de forçar a resposta final.
# Segura loop de modelo que fica repedindo a mesma ferramenta.
LLM_MAX_TOOL_ITERACOES = env.int("LLM_MAX_TOOL_ITERACOES", default=2)

# Embeddings também via Ollama — evita arrastar torch/sentence-transformers
# (~2,3 GB) para dentro da imagem Django. `all-minilm` é a mesma família
# escolhida no ADR-0004 e produz **384 dimensões**, então a coluna
# FAQ_VECTOR.EMBEDDING não muda.
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", default="ollama")
EMBEDDING_BASE_URL = env("EMBEDDING_BASE_URL", default="http://host.docker.internal:11434")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="all-minilm")
# Precisa bater com a dimensão declarada na migration da coluna VECTOR.
# Mudar aqui sem migrar + reindexar devolve resultado errado silenciosamente.
EMBEDDING_DIM = env.int("EMBEDDING_DIM", default=384)

# Teto de duração de um turno de chat (rede de segurança para não prender
# worker indefinidamente) e de histórico reenviado ao modelo. O contexto real
# do Ollama é 4096 tokens, bem abaixo do que o modelo anuncia — histórico
# longo faz o system prompt (com os guardrails) ser descartado silenciosamente.
CHAT_STREAM_MAX_SEGUNDOS = env.int("CHAT_STREAM_MAX_SEGUNDOS", default=120)
CHAT_HISTORICO_MAX_TURNOS = env.int("CHAT_HISTORICO_MAX_TURNOS", default=6)

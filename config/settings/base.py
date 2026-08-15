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
# ``oracle://user:password@host:port/SERVICE_NAME``. O default aponta para o
# serviço ``oracle`` do compose, evitando explosão silenciosa em
# ``manage.py check`` — qualquer operação real ainda precisa do Oracle no ar.
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="oracle://clinicos:oracle@oracle:1521/FREEPDB1",
    ),
}


def _normalizar_dsn_oracle(cfg: dict) -> None:
    """Converte HOST/PORT/NAME para uma string EZConnect no ``NAME``.

    O backend Oracle do Django monta o DSN assim (``django/db/backends/oracle/
    base.py``)::

        if settings_dict["PORT"]:
            return makedsn(host, int(port), settings_dict["NAME"])
        return settings_dict["NAME"]

    O terceiro argumento de ``makedsn`` é o **SID**, não o service name. Como o
    Oracle 23ai Free expõe o PDB por *service name* (``FREEPDB1``), deixar
    ``PORT`` preenchido produz ``DPY-6003: SID "FREEPDB1" is not registered``.

    Esvaziando ``PORT`` e passando ``host:port/service`` em ``NAME``, o Django
    devolve a string intacta e o ``python-oracledb`` a interpreta como
    EZConnect — onde o que vem depois da barra é o service name. É o caminho
    suportado para PDB.

    Nota: não adianta pôr ``service_name`` em ``OPTIONS``. Aquele dict é
    repassado como ``**kwargs`` para ``oracledb.connect()`` junto com o ``dsn``,
    o que é ambíguo. É também por isso que a URL usa ``/FREEPDB1`` no path e não
    ``?service_name=FREEPDB1``: para Oracle com path vazio, o django-environ
    move o hostname para ``NAME`` e **zera o HOST**, e a conexão vai parar em
    localhost.
    """
    if "oracle" not in cfg.get("ENGINE", "") or not cfg.get("PORT"):
        return
    host = (cfg.get("HOST") or "localhost").strip()
    cfg["NAME"] = f"{host}:{cfg['PORT']}/{cfg['NAME']}"
    cfg["PORT"] = ""


_normalizar_dsn_oracle(DATABASES["default"])


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

# O default do Django é ``/accounts/login/``, rota que este projeto **não** tem:
# a única tela de login é a do Admin (ADR-0005). Sem isto, qualquer view com
# ``@login_required`` — a grade da agenda `[S4-4]` é a primeira — manda o
# usuário deslogado para um 404. Aponta para o nome da rota, e não para o
# caminho, para que um eventual remapeamento do prefixo do Admin acompanhe.
LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "agenda:consultas"


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
# Multilíngue, e não o `all-minilm` do spike. Aquele é treinado em inglês e,
# medido contra a FAQ da clínica, casava por sobreposição lexical em português
# ("que horas vocês abrem?" trazia "Vocês atendem pelo SUS?"). Numa baseline de
# 8 paráfrases: all-minilm 6/8, paraphrase-multilingual 8/8.
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="paraphrase-multilingual")
# Precisa bater com a dimensão declarada na migration da coluna VECTOR.
# Mudar aqui sem migrar + reindexar devolve resultado errado silenciosamente —
# é o que `FaqVector.embedding_dim` e a checagem do repositório protegem.
EMBEDDING_DIM = env.int("EMBEDDING_DIM", default=768)

# Teto de duração de um turno de chat (rede de segurança para não prender
# worker indefinidamente) e de histórico reenviado ao modelo. O contexto real
# do Ollama é 4096 tokens, bem abaixo do que o modelo anuncia — histórico
# longo faz o system prompt (com os guardrails) ser descartado silenciosamente.
CHAT_STREAM_MAX_SEGUNDOS = env.int("CHAT_STREAM_MAX_SEGUNDOS", default=120)
CHAT_HISTORICO_MAX_TURNOS = env.int("CHAT_HISTORICO_MAX_TURNOS", default=6)

"""Settings para execução de testes (``pytest`` / ``make test``).

Herda tudo de ``base.py`` e otimiza para rapidez:

- Hasher MD5 (não usar em produção!) para pular custo de Argon2/PBKDF2.
- Email em memória (``locmem``) — testes podem inspecionar ``mail.outbox``.
- Celery síncrono (``CELERY_TASK_ALWAYS_EAGER``) — tasks rodam inline na
  mesma thread do teste.
- **Banco SQLite em memória** — CI roda sem Oracle (ver decisão abaixo).

Cadeia de herança: ``base.py`` → ``test.py``.
Selecione com ``DJANGO_SETTINGS_MODULE=config.settings.test`` (configurado em
``pyproject.toml`` / ``pytest.ini`` — vide S1-24).

Por que SQLite? (S1-24)
-----------------------
Subir Oracle 23ai como service container no GitHub Actions é caro: a imagem
oficial passa de 8GB, o healthcheck é lento e instável, e a maioria dos testes
unitários da Sprint 1 não toca em PL/SQL nem em vetores. SQLite em memória
serve para validar lógica de domínio em milissegundos.

Testes de integração que dependem de features específicas do Oracle
(trigger PL/SQL de imutabilidade — S1-10; constraint UNIQUE de slot — S1-11;
índice HNSW em ``FAQ_VECTOR.EMBEDDING`` — S1-12) deverão ser marcados com
``@pytest.mark.oracle`` e rodam apenas em ambiente local/staging com Oracle.
O CI ignora esses marcadores via ``-m "not oracle"`` quando essa suíte existir
(decisão fica para a sprint de QA quando os testes Oracle aparecerem).
"""

from __future__ import annotations

from .base import *  # noqa: F401,F403

DEBUG = False

# Hashing rápido — segurança não importa em teste, velocidade sim.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Captura emails em memória para asserts via ``django.core.mail.outbox``.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Tasks Celery síncronas e propagam exceções para o teste.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ---------------------------------------------------------------------------
# IA: nada de rede na suíte padrão
# ---------------------------------------------------------------------------
# Sem estes dois overrides, a suíte herda `ollama` da base e passa a depender
# de um serviço externo **sem declarar isso**. O sintoma é traiçoeiro: em
# máquina de dev, onde o container alcança o Ollama, os testes ficam verdes por
# acidente; no CI, que não tem GPU nem Ollama, quebram com
# `URLError: Name or service not known`. Foi exatamente assim que dois testes
# de `buscar_faq` passaram local e reprovaram no CI.
#
# Os testes que **precisam** do modelo real são explícitos: marcados com
# `@pytest.mark.llm` e instanciando o provedor Ollama à mão. Rode com
# `make test-llm`.
LLM_PROVIDER = "fake"
EMBEDDING_PROVIDER = "fake"

# ---------------------------------------------------------------------------
# Banco de testes
# ---------------------------------------------------------------------------
# Override total do DATABASES — SQLite em memória, rápido e sem dependência
# externa. CI roda com isso; dev local também (basta exportar
# DJANGO_SETTINGS_MODULE=config.settings.test). Testes de integração com
# Oracle ficam em apps específicos com ``@pytest.mark.oracle`` (futuro).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

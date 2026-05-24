"""Settings para execução de testes (``pytest`` / ``make test``).

Herda tudo de ``base.py`` e otimiza para rapidez:

- Hasher MD5 (não usar em produção!) para pular custo de Argon2/PBKDF2.
- Email em memória (``locmem``) — testes podem inspecionar ``mail.outbox``.
- Celery síncrono (``CELERY_TASK_ALWAYS_EAGER``) — tasks rodam inline na
  mesma thread do teste.

Cadeia de herança: ``base.py`` → ``test.py``.
Selecione com ``DJANGO_SETTINGS_MODULE=config.settings.test`` (configurado em
``pyproject.toml`` / ``pytest.ini`` quando S1-24 ativar CI).

TODO: hoje os testes ainda apontam para o Oracle definido em ``base.py``.
Avaliar:
- usar um schema/PDB de teste separado (ex.: ``FREEPDB1_TEST``), ou
- trocar ``DATABASES`` para SQLite aqui dentro caso os testes não dependam de
  features específicas do Oracle (PL/SQL, HNSW, etc.). Como o domínio tem
  triggers PL/SQL (S1-10) e índice HNSW (S1-12), SQLite *não* serve para a
  suíte completa. Decisão fica para a sprint de QA.
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

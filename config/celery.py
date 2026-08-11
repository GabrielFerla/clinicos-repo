"""Aplicação Celery do ClinicOS.

O ``docker-compose.yml`` e o ``Makefile`` chamam ``celery -A config worker``,
o que exige um objeto ``app`` importável a partir do pacote ``config`` — ver
``config/__init__.py``.

O chatbot do MVP1 não usa fila (o turno é síncrono, dentro do request). O
Celery entra aqui porque as tarefas assíncronas das próximas sprints já estão
previstas — e-mail de confirmação, lembrete D-1, geração de slots — e porque
sem este módulo o serviço ``celery-worker`` do compose fica em crash-loop,
consumindo recursos à toa durante o desenvolvimento.
"""

from __future__ import annotations

import os

from celery import Celery

# Mesmo default do ``manage.py``: em dev nada precisa exportar a variável.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("clinicos")

# ``namespace="CELERY"`` faz o Celery ler as chaves do settings do Django que
# começam com ``CELERY_`` (CELERY_BROKER_URL, CELERY_TIMEZONE etc.), evitando
# uma segunda fonte de verdade de configuração.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Descobre ``tasks.py`` em cada app de INSTALLED_APPS.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Task trivial para validar que o worker está vivo e consome a fila."""
    print(f"Request: {self.request!r}")  # noqa: T201 — diagnóstico do worker

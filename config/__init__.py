"""Pacote de configuração do ClinicOS.

O import do ``celery_app`` precisa acontecer aqui para que o Celery seja
inicializado junto com o Django — é o que permite ``@shared_task`` funcionar
nos apps e ``celery -A config worker`` encontrar a aplicação.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)

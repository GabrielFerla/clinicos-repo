"""Pacote de settings do ClinicOS.

Atualmente carrega o placeholder mínimo (`_placeholder.py`) apenas para permitir
que `python manage.py check` rode antes da divisão final de settings.

S1-6 substituirá este import por `base/dev/prod/test` propriamente divididos e
selecionados via `DJANGO_SETTINGS_MODULE` (ex.: `config.settings.dev`).
"""

from ._placeholder import *  # noqa: F401,F403

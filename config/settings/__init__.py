"""Pacote de settings do ClinicOS.

A partir da S1-6 este pacote NÃO importa nenhum módulo automaticamente. O
ambiente é escolhido via variável `DJANGO_SETTINGS_MODULE`:

- `config.settings.dev`  → desenvolvimento local (default em ``manage.py``)
- `config.settings.test` → execução de testes (``pytest``/``make test``)
- `config.settings.prod` → produção
- `config.settings.base` → não usar diretamente; é apenas a base herdada

A configuração compartilhada vive em ``base.py``. Cada ambiente faz
``from .base import *`` e sobrescreve apenas o necessário.
"""

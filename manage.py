#!/usr/bin/env python
"""Utilitário de linha de comando do Django para o ClinicOS."""

import os
import sys


def main() -> None:
    """Executa tarefas administrativas."""
    # Default aponta para o módulo de settings dividido em S1-6. Por enquanto
    # `config.settings` carrega `_placeholder.py` apenas para permitir `check`.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Não foi possível importar o Django. Verifique se ele está instalado "
            "e disponível no PYTHONPATH. O virtualenv está ativo?"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

"""Configuração global do pytest para o ClinicOS.

Este arquivo existe para **pular os testes que exigem serviço externo** — ver
``pytest_collection_modifyitems``.

O que ele **não** faz, e por quê
--------------------------------
Este conftest já teve ``os.environ.setdefault`` para ``DJANGO_SECRET_KEY``,
``CPF_ENCRYPTION_KEY`` e ``CPF_HASH_PEPPER``, na crença de que conftests da raiz
são importados antes de o ``pytest-django`` chamar ``django.setup()``. **É o
contrário**: o ``django.setup()`` acontece em ``pytest_load_initial_conftests``,
antes deste módulo ser importado, então qualquer ``setdefault`` daqui chega
depois de as settings já terem congelado o valor. Medido: no mesmo processo,
``os.environ`` tinha o pepper e ``settings.CPF_HASH_PEPPER`` era ``None``.

Aqueles três ``setdefault`` não protegiam ninguém — e, pior, davam a impressão
de proteger, o que levou a apagar as chaves do workflow e deixar o CI vermelho
por 4 runs. Hoje cada valor vem de onde é avaliado na hora certa:

- ``CPF_ENCRYPTION_KEY`` / ``CPF_HASH_PEPPER`` — ``config/settings/test.py``.
- ``DJANGO_SECRET_KEY`` — do ambiente (``docker-compose.yml`` em dev, bloco
  ``env:`` do workflow no CI). ``base.py`` o lê sem default de propósito, e numa
  máquina sem ``.env`` o ``pytest`` para na hora com a mensagem certa. É o
  comportamento desejado, não um bug a contornar.
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Auto-skip por marker
# ---------------------------------------------------------------------------
# Cada entrada mapeia o marker para a variável que o habilita.
_MARKERS_EXTERNOS = {
    "oracle": (
        "CLINICOS_TEST_ORACLE",
        "precisa de Oracle 23ai real (VECTOR/PL-SQL); habilite com CLINICOS_TEST_ORACLE=1",
    ),
    "llm": (
        "CLINICOS_TEST_LLM",
        "precisa do Ollama no host; habilite com CLINICOS_TEST_LLM=1",
    ),
}


def pytest_collection_modifyitems(config, items):
    """Pula testes que dependem de serviço externo, salvo se explicitamente habilitados.

    Preferimos auto-skip aqui a ``-m "not oracle"`` apenas no CI: assim quem
    roda ``pytest`` na mão, sem Oracle nem Ollama de pé, também tem uma suíte
    verde em vez de uma pilha de erros de conexão.

    O caminho inverso é explícito — ``CLINICOS_TEST_ORACLE=1 pytest -m oracle``
    — o que evita que esses testes deixem de rodar silenciosamente para sempre.
    """
    for marker, (env_var, motivo) in _MARKERS_EXTERNOS.items():
        if os.environ.get(env_var) == "1":
            continue
        skip = pytest.mark.skip(reason=motivo)
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)

"""Configuração global do pytest para o ClinicOS.

Este arquivo existe por dois motivos, ambos não-óbvios:

1. **Defaults de ambiente antes do ``django.setup()``.**
   ``config/settings/base.py`` lê ``DJANGO_SECRET_KEY`` **sem default** — de
   propósito, para falhar rápido em ambiente real. O efeito colateral é que
   ``pytest`` numa máquina limpa (sem ``.env``, sem env vars exportadas) morre
   com ``ImproperlyConfigured`` antes de coletar o primeiro teste.

   Os ``os.environ.setdefault`` abaixo rodam **no nível de módulo**, e não
   dentro de uma fixture, porque conftests da raiz são importados *antes* do
   ``pytest_configure`` do ``pytest-django`` — que é onde o ``django.setup()``
   acontece. Numa fixture seria tarde demais.

   ``setdefault`` (e não atribuição direta) preserva o que o CI ou o dev já
   tiver exportado.

2. **Auto-skip dos testes que exigem serviço externo.**
   Ver ``pytest_collection_modifyitems``.
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Defaults de ambiente (ver docstring, item 1)
# ---------------------------------------------------------------------------
# Valores descartáveis, exclusivos de teste. A chave e o pepper têm o formato
# que ``CPFCipher.from_urlsafe`` e ``cpf_hash`` esperam (base64-urlsafe de 32
# bytes), mas nenhum valor real jamais deve aparecer aqui.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key-nao-use-fora-de-teste")
os.environ.setdefault("CPF_ENCRYPTION_KEY", "Y2xpbmljb3MtdGVzdC1vbmx5LWtleS0zMmJ5dGVzISE")
os.environ.setdefault("CPF_HASH_PEPPER", "Y2xpbmljb3MtdGVzdC1vbmx5LXBlcHBlci0zMmJ5dGU")


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

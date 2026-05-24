"""Helpers para geração/rotação de chaves cripto.

Uso pontual (operacional, não chamado em runtime). Mantemos separado de
``crypto.py`` para deixar claro que importar este módulo num path de request
é cheiro de código.
"""

from __future__ import annotations

from .crypto import CPFCipher


def generate_cpf_key_for_env() -> str:
    """Retorna uma chave AES-256 nova em base64-urlsafe, pronta para colar no ``.env``.

    Uso manual::

        python -c "from apps.core.security.keys import generate_cpf_key_for_env; \\
                   print(generate_cpf_key_for_env())"
    """
    return CPFCipher.generate_key_urlsafe()

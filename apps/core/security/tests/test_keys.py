"""Testes unitários do helper ``apps.core.security.keys`` (S1-15).

Cobre ``generate_cpf_key_for_env``: tipo de retorno, decodificação como
base64-urlsafe, comprimento de 32 bytes e unicidade entre chamadas.
"""

from __future__ import annotations

import base64

from apps.core.security.crypto import CPFCipher
from apps.core.security.keys import generate_cpf_key_for_env


def test_generate_cpf_key_for_env_returns_str() -> None:
    key = generate_cpf_key_for_env()
    assert isinstance(key, str)


def test_generate_cpf_key_for_env_decodes_to_32_bytes() -> None:
    """Chave deve ser base64-urlsafe que decodifica em exatamente 32 bytes."""
    key = generate_cpf_key_for_env()
    # Re-adiciona padding antes de decodificar (helper remove ``=``).
    decoded = base64.urlsafe_b64decode(key + "==")
    assert len(decoded) == 32


def test_generate_cpf_key_for_env_has_no_padding() -> None:
    """Convenção do projeto: chaves do ``.env`` não levam ``=``."""
    key = generate_cpf_key_for_env()
    assert "=" not in key


def test_generate_cpf_key_for_env_produces_distinct_keys() -> None:
    """20 chamadas seguidas devem dar 20 chaves diferentes (CSPRNG)."""
    keys = {generate_cpf_key_for_env() for _ in range(20)}
    assert len(keys) == 20


def test_generated_key_is_usable_by_cpf_cipher() -> None:
    """A chave gerada serve para construir um CPFCipher funcional."""
    key = generate_cpf_key_for_env()
    cipher = CPFCipher.from_urlsafe(key)
    token = cipher.encrypt("12345678900")
    assert cipher.decrypt(token) == "12345678900"

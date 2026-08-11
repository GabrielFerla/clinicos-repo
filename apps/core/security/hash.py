"""Hash determinístico HMAC-SHA256 com pepper para busca/comparação de PII.

Use para:
  - Busca: WHERE cpf_hash = :h
  - Unicidade: UNIQUE INDEX em cpf_hash
  - Comparação sem revelar o CPF em logs

Stateless. Pepper passado como parâmetro; nunca lido de env diretamente —
o caller (ex.: settings.CPF_HASH_PEPPER) decide a fonte.
"""

from __future__ import annotations

import hashlib
import hmac
import re

_CPF_DIGITS_RE = re.compile(r"\D+")


def normalize_cpf(cpf: str) -> str:
    """Remove pontuação e espaços; valida 11 dígitos.

    Levanta ValueError se não ficar com 11 dígitos numéricos.
    Não valida o dígito verificador (responsabilidade da camada de modelo/form).
    """
    if not isinstance(cpf, str):
        raise TypeError("cpf deve ser str.")
    digits = _CPF_DIGITS_RE.sub("", cpf)
    if len(digits) != 11 or not digits.isdigit():
        raise ValueError("CPF deve ter exatamente 11 dígitos numéricos.")
    return digits


def cpf_hash(cpf: str, pepper: bytes) -> str:
    """Hash HMAC-SHA256 hexa do CPF normalizado, usando pepper.

    Args:
        cpf: string com ou sem pontuação. Normalizada internamente.
        pepper: bytes secretos (>=32 bytes recomendado).

    Returns:
        hex string de 64 caracteres (256 bits).

    Raises:
        ValueError: se CPF não tiver 11 dígitos.
        TypeError: se pepper não for bytes.
    """
    if not isinstance(pepper, (bytes, bytearray)) or len(pepper) < 16:
        raise TypeError("pepper deve ser bytes com >=16 bytes (recomendado >=32).")
    digits = normalize_cpf(cpf)
    mac = hmac.new(bytes(pepper), digits.encode("ascii"), hashlib.sha256)
    return mac.hexdigest()


def verify_cpf_hash(cpf: str, expected_hash: str, pepper: bytes) -> bool:
    """Compara CPF candidato com hash esperado em tempo constante.

    Use sempre esta função em vez de == direto para evitar timing attacks.
    """
    try:
        computed = cpf_hash(cpf, pepper)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(computed, expected_hash)

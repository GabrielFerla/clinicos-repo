"""Hash determinístico HMAC-SHA256 com pepper para busca/comparação de PII.

Use para:
  - Busca: WHERE cpf_hash = :h
  - Unicidade: UNIQUE INDEX em cpf_hash
  - Comparação sem revelar o CPF em logs

Stateless. Pepper passado como parâmetro; nunca lido de env diretamente —
o caller (ex.: settings.CPF_HASH_PEPPER) decide a fonte.

Junto com o hash moram os dois helpers de forma do CPF — ``normalize_cpf``
(11 dígitos) e ``validar_cpf`` (dígitos verificadores). Ficam aqui, e não num
módulo de validação à parte, porque são pré-requisito do hash: o que entra em
``cpf_hash`` já passou por ``normalize_cpf``, e quem cadastra passa antes por
``validar_cpf``.
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


def validar_cpf(cpf: str) -> bool:
    """Valida os dois dígitos verificadores pelo algoritmo oficial da Receita.

    Complemento de :func:`normalize_cpf`, que só confere a quantidade de
    dígitos: ``"11111111111"`` e ``"12345678900"`` passam lá e são recusados
    aqui. A separação é deliberada — a normalização é pré-requisito de
    ``cpf_hash`` (que precisa aceitar qualquer string de 11 dígitos para
    conseguir *buscar*), enquanto a validação de DV é regra de cadastro, e só
    o formulário de entrada precisa dela.

    Os dígitos repetidos (``00000000000``, ``11111111111``, …) são rejeitados
    explicitamente: eles satisfazem a aritmética dos verificadores por acidente
    (todo somatório vira múltiplo de 11) e são a forma clássica de burlar uma
    validação implementada só com o algoritmo.

    Args:
        cpf: String com ou sem pontuação. Normalizada internamente.

    Returns:
        ``True`` se o CPF tem 11 dígitos e os dois verificadores conferem.
        ``False`` em qualquer outro caso — inclusive entrada malformada ou de
        tipo errado. **Não levanta**, pelo mesmo motivo de
        :func:`verify_cpf_hash`: quem chama está validando entrada de usuário e
        quer um booleano, não um ``try/except``.
    """
    try:
        digits = normalize_cpf(cpf)
    except (TypeError, ValueError):
        return False
    if digits == digits[0] * 11:
        return False
    for tamanho in (9, 10):
        # Pesos decrescentes a partir de ``tamanho + 1``: 10..2 para o primeiro
        # verificador, 11..2 para o segundo (que já inclui o primeiro no cálculo).
        soma = sum(int(d) * (tamanho + 1 - i) for i, d in enumerate(digits[:tamanho]))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(digits[tamanho]):
            return False
    return True


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

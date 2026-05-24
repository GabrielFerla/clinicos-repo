"""Testes unitários do helper ``apps.core.security.hash`` (S1-15).

Cobre ``normalize_cpf``, ``cpf_hash`` e ``verify_cpf_hash``:
- normalização de formatos válidos / inválidos;
- determinismo do hash com mesma chave/pepper;
- detecção de mudança no pepper;
- comparação em tempo constante.

Testes puros (não tocam Django/Oracle).
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from apps.core.security.hash import cpf_hash, normalize_cpf, verify_cpf_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pepper() -> bytes:
    """Pepper de 32 bytes para testes (acima do mínimo de 16)."""
    return b"\xa1" * 32


@pytest.fixture
def other_pepper() -> bytes:
    return b"\xb2" * 32


# ---------------------------------------------------------------------------
# normalize_cpf — formatos válidos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "123.456.789-00",
        "12345678900",
        "123 456 789 00",
        "  12345678900  ",
        "123-456-789-00",
        "123.456.789.00",
        "\t123 456 789-00\n",
    ],
)
def test_normalize_cpf_strips_punctuation(raw: str) -> None:
    assert normalize_cpf(raw) == "12345678900"


def test_normalize_cpf_preserves_leading_zeros() -> None:
    """CPFs podem começar com 0 — não devem ser truncados."""
    assert normalize_cpf("000.000.000-00") == "00000000000"


def test_normalize_cpf_returns_str() -> None:
    result = normalize_cpf("12345678900")
    assert isinstance(result, str)
    assert len(result) == 11


# ---------------------------------------------------------------------------
# normalize_cpf — inválidos (ValueError)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "",
        "1234567890",  # 10 dígitos
        "123456789012",  # 12 dígitos
        "abc.def.ghi-jk",  # 11 chars mas não-dígitos
        "1234567890a",  # 10 dígitos + letra (vira 10 dígitos após strip)
        "1.2.3.4",
        "123.456.789-0X",
    ],
)
def test_normalize_cpf_invalid_raises_value_error(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_cpf(raw)


# ---------------------------------------------------------------------------
# normalize_cpf — tipos inválidos (TypeError)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        b"12345678900",
        None,
        12345678900,
        12.5,
        ["12345678900"],
        {"cpf": "12345678900"},
    ],
)
def test_normalize_cpf_wrong_type_raises_type_error(bad: object) -> None:
    with pytest.raises(TypeError):
        normalize_cpf(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cpf_hash — propriedades de determinismo
# ---------------------------------------------------------------------------


def test_cpf_hash_is_deterministic(pepper: bytes) -> None:
    """Mesmo CPF + mesmo pepper → mesmo hash em chamadas independentes."""
    assert cpf_hash("12345678900", pepper) == cpf_hash("12345678900", pepper)


def test_cpf_hash_normalizes_input(pepper: bytes) -> None:
    """CPF formatado e bruto produzem o mesmo hash (graças à normalização)."""
    assert cpf_hash("123.456.789-00", pepper) == cpf_hash("12345678900", pepper)


def test_cpf_hash_normalizes_input_with_spaces(pepper: bytes) -> None:
    assert cpf_hash("  123 456 789 00  ", pepper) == cpf_hash("12345678900", pepper)


def test_cpf_hash_length_is_64_hex_chars(pepper: bytes) -> None:
    """SHA-256 → 32 bytes → 64 chars hex."""
    h = cpf_hash("12345678900", pepper)
    assert len(h) == 64
    assert isinstance(h, str)
    # Todos os caracteres são hex válidos.
    int(h, 16)


def test_cpf_hash_is_lowercase_hex(pepper: bytes) -> None:
    """hexdigest() retorna minúsculo — documentado pelo helper."""
    h = cpf_hash("12345678900", pepper)
    assert h == h.lower()


# ---------------------------------------------------------------------------
# cpf_hash — sensibilidade a CPF e a pepper
# ---------------------------------------------------------------------------


def test_cpf_hash_different_cpfs_yield_different_hashes(pepper: bytes) -> None:
    assert cpf_hash("12345678900", pepper) != cpf_hash("12345678901", pepper)


def test_cpf_hash_single_digit_change_yields_different_hash(pepper: bytes) -> None:
    """Avalanche: mudar 1 dígito muda o hash inteiro."""
    h1 = cpf_hash("12345678900", pepper)
    h2 = cpf_hash("12345678901", pepper)
    assert h1 != h2


def test_cpf_hash_different_peppers_yield_different_hashes(
    pepper: bytes, other_pepper: bytes
) -> None:
    """Mesmo CPF + peppers distintos → hashes distintos."""
    assert cpf_hash("12345678900", pepper) != cpf_hash("12345678900", other_pepper)


def test_cpf_hash_matches_reference_implementation(pepper: bytes) -> None:
    """Sanidade: o output bate com HMAC-SHA256 puro do hmac stdlib."""
    expected = hmac.new(pepper, b"12345678900", hashlib.sha256).hexdigest()
    assert cpf_hash("12345678900", pepper) == expected


def test_cpf_hash_accepts_bytearray_pepper() -> None:
    """bytearray também é aceito (subclasse de bytes-like)."""
    pp = bytearray(b"x" * 32)
    h = cpf_hash("12345678900", pp)
    assert len(h) == 64


def test_cpf_hash_accepts_pepper_exactly_16_bytes() -> None:
    """16 bytes é o mínimo permitido."""
    pp = b"y" * 16
    h = cpf_hash("12345678900", pp)
    assert len(h) == 64


# ---------------------------------------------------------------------------
# cpf_hash — pepper inválido (TypeError)
# ---------------------------------------------------------------------------


def test_cpf_hash_str_pepper_raises_type_error() -> None:
    with pytest.raises(TypeError):
        cpf_hash("12345678900", "a" * 32)  # type: ignore[arg-type]


def test_cpf_hash_short_pepper_raises_type_error() -> None:
    """Pepper de 15 bytes (1 abaixo do mínimo) → TypeError."""
    with pytest.raises(TypeError):
        cpf_hash("12345678900", b"x" * 15)


def test_cpf_hash_empty_pepper_raises_type_error() -> None:
    with pytest.raises(TypeError):
        cpf_hash("12345678900", b"")


def test_cpf_hash_none_pepper_raises_type_error() -> None:
    with pytest.raises(TypeError):
        cpf_hash("12345678900", None)  # type: ignore[arg-type]


def test_cpf_hash_int_pepper_raises_type_error() -> None:
    with pytest.raises(TypeError):
        cpf_hash("12345678900", 12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cpf_hash — CPF inválido propaga ValueError
# ---------------------------------------------------------------------------


def test_cpf_hash_invalid_cpf_raises_value_error(pepper: bytes) -> None:
    """CPF curto propaga o ValueError de normalize_cpf."""
    with pytest.raises(ValueError):
        cpf_hash("1234", pepper)


def test_cpf_hash_non_str_cpf_raises_type_error(pepper: bytes) -> None:
    """CPF bytes propaga TypeError de normalize_cpf."""
    with pytest.raises(TypeError):
        cpf_hash(b"12345678900", pepper)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# verify_cpf_hash
# ---------------------------------------------------------------------------


def test_verify_cpf_hash_match_returns_true(pepper: bytes) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("12345678900", h, pepper) is True


def test_verify_cpf_hash_match_with_formatted_cpf(pepper: bytes) -> None:
    """Normalização aplicada antes da comparação."""
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("123.456.789-00", h, pepper) is True


def test_verify_cpf_hash_mismatch_returns_false(pepper: bytes) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("12345678901", h, pepper) is False


def test_verify_cpf_hash_wrong_pepper_returns_false(
    pepper: bytes, other_pepper: bytes
) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("12345678900", h, other_pepper) is False


def test_verify_cpf_hash_invalid_cpf_returns_false(pepper: bytes) -> None:
    """CPF inválido NÃO levanta — retorna False (API documentada)."""
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("abc", h, pepper) is False


def test_verify_cpf_hash_empty_cpf_returns_false(pepper: bytes) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("", h, pepper) is False


def test_verify_cpf_hash_short_cpf_returns_false(pepper: bytes) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("1234567890", h, pepper) is False


def test_verify_cpf_hash_invalid_pepper_returns_false() -> None:
    """Pepper inválido (str) → False, sem levantar."""
    # Hash arbitrário; o que importa é que verify não estoure com pepper ruim.
    fake_hash = "0" * 64
    assert verify_cpf_hash("12345678900", fake_hash, "not-bytes") is False  # type: ignore[arg-type]


def test_verify_cpf_hash_short_pepper_returns_false() -> None:
    fake_hash = "0" * 64
    assert verify_cpf_hash("12345678900", fake_hash, b"x" * 15) is False


def test_verify_cpf_hash_none_pepper_returns_false() -> None:
    fake_hash = "0" * 64
    assert verify_cpf_hash("12345678900", fake_hash, None) is False  # type: ignore[arg-type]


def test_verify_cpf_hash_non_str_cpf_returns_false(pepper: bytes) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash(b"12345678900", h, pepper) is False  # type: ignore[arg-type]


def test_verify_cpf_hash_is_case_sensitive(pepper: bytes) -> None:
    """`compare_digest` é case-sensitive; hash uppercase != lowercase."""
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("12345678900", h.upper(), pepper) is False


def test_verify_cpf_hash_empty_expected_returns_false(pepper: bytes) -> None:
    assert verify_cpf_hash("12345678900", "", pepper) is False


def test_verify_cpf_hash_truncated_expected_returns_false(pepper: bytes) -> None:
    h = cpf_hash("12345678900", pepper)
    assert verify_cpf_hash("12345678900", h[:-1], pepper) is False

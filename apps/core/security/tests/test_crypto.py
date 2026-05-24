"""Testes unitários do helper ``apps.core.security.crypto`` (S1-15).

Cobre ``CPFCipher``: encrypt/decrypt happy path, não-determinismo do token
(nonce aleatório), AAD binding, tampering, validação de chave, round-trip
urlsafe, geração de chaves e tratamento de tipos/tamanhos inválidos.

Estes testes são puros (sem Django/Oracle): rodam só com ``cryptography``
instalado. Importam direto de ``apps.core.security.crypto`` para isolar o
helper das settings.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidTag

from apps.core.security.crypto import CPFCipher, InvalidKeyError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def key() -> bytes:
    """Chave AES-256 determinística para testes (32 bytes)."""
    return b"\x00" * 16 + b"\xff" * 16


@pytest.fixture
def cipher(key: bytes) -> CPFCipher:
    return CPFCipher(key)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_round_trip(cipher: CPFCipher) -> None:
    plaintext = "12345678900"
    token = cipher.encrypt(plaintext)
    assert cipher.decrypt(token) == plaintext


def test_decrypt_returns_str(cipher: CPFCipher) -> None:
    token = cipher.encrypt("12345678900")
    result = cipher.decrypt(token)
    assert isinstance(result, str)


def test_round_trip_with_punctuation(cipher: CPFCipher) -> None:
    """CPF formatado também faz round-trip (cipher não normaliza)."""
    plaintext = "123.456.789-00"
    assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext


def test_same_key_decrypts_independent_instances(key: bytes) -> None:
    """Determinismo da chave: instância A criptografa, instância B descriptografa."""
    cipher_a = CPFCipher(key)
    cipher_b = CPFCipher(key)
    token = cipher_a.encrypt("12345678900")
    assert cipher_b.decrypt(token) == "12345678900"


# ---------------------------------------------------------------------------
# Não-determinismo do token (nonce aleatório)
# ---------------------------------------------------------------------------


def test_encrypt_produces_different_tokens_for_same_plaintext(cipher: CPFCipher) -> None:
    """Duas chamadas com mesmo input geram tokens diferentes (nonce aleatório)."""
    token_a = cipher.encrypt("12345678900")
    token_b = cipher.encrypt("12345678900")
    assert token_a != token_b
    # Mas ambos decifram para o mesmo plaintext.
    assert cipher.decrypt(token_a) == cipher.decrypt(token_b) == "12345678900"


def test_encrypt_many_calls_all_distinct(cipher: CPFCipher) -> None:
    """Sanidade extra: 20 chamadas com mesmo plaintext = 20 tokens distintos."""
    tokens = {cipher.encrypt("x") for _ in range(20)}
    assert len(tokens) == 20


# ---------------------------------------------------------------------------
# AAD binding
# ---------------------------------------------------------------------------


def test_aad_match_round_trip(cipher: CPFCipher) -> None:
    token = cipher.encrypt("12345678900", aad=b"patient-42")
    assert cipher.decrypt(token, aad=b"patient-42") == "12345678900"


def test_aad_mismatch_raises_invalid_tag(cipher: CPFCipher) -> None:
    token = cipher.encrypt("12345678900", aad=b"patient-42")
    with pytest.raises(InvalidTag):
        cipher.decrypt(token, aad=b"patient-99")


def test_decrypt_without_aad_when_encrypted_with_aad_fails(cipher: CPFCipher) -> None:
    token = cipher.encrypt("12345678900", aad=b"patient-42")
    with pytest.raises(InvalidTag):
        cipher.decrypt(token)


def test_no_aad_round_trip(cipher: CPFCipher) -> None:
    token = cipher.encrypt("12345678900")
    assert cipher.decrypt(token) == "12345678900"


def test_decrypt_with_aad_when_encrypted_without_aad_fails(cipher: CPFCipher) -> None:
    """Binding assimétrico: sem AAD na cifra, mas AAD no decifra → InvalidTag."""
    token = cipher.encrypt("12345678900")
    with pytest.raises(InvalidTag):
        cipher.decrypt(token, aad=b"x")


# ---------------------------------------------------------------------------
# Tampering
# ---------------------------------------------------------------------------


def test_tampered_token_raises_invalid_tag(cipher: CPFCipher) -> None:
    """Flip 1 byte do token → InvalidTag na decifra (autenticação GCM)."""
    token = cipher.encrypt("12345678900")
    raw = bytearray(base64.urlsafe_b64decode(token + "=="))
    # Altera 1 byte no meio do ciphertext (depois do nonce de 12 bytes).
    raw[15] ^= 0x01
    tampered = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()
    with pytest.raises(InvalidTag):
        cipher.decrypt(tampered)


def test_tampered_tag_raises_invalid_tag(cipher: CPFCipher) -> None:
    """Tampering nos últimos bytes (a tag GCM) também é detectado."""
    token = cipher.encrypt("12345678900")
    raw = bytearray(base64.urlsafe_b64decode(token + "=="))
    raw[-1] ^= 0x01  # último byte = parte da tag de 16 bytes
    tampered = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()
    with pytest.raises(InvalidTag):
        cipher.decrypt(tampered)


# ---------------------------------------------------------------------------
# Validação de chave
# ---------------------------------------------------------------------------


def test_key_short_raises_invalid_key_error() -> None:
    with pytest.raises(InvalidKeyError):
        CPFCipher(b"\x00" * 31)


def test_key_long_raises_invalid_key_error() -> None:
    with pytest.raises(InvalidKeyError):
        CPFCipher(b"\x00" * 33)


def test_key_empty_raises_invalid_key_error() -> None:
    with pytest.raises(InvalidKeyError):
        CPFCipher(b"")


def test_key_str_raises_invalid_key_error() -> None:
    """Chave deve ser bytes, não str — mesmo que str tenha 32 chars."""
    with pytest.raises(InvalidKeyError):
        CPFCipher("a" * 32)  # type: ignore[arg-type]


def test_key_none_raises_invalid_key_error() -> None:
    with pytest.raises(InvalidKeyError):
        CPFCipher(None)  # type: ignore[arg-type]


def test_key_int_raises_invalid_key_error() -> None:
    with pytest.raises(InvalidKeyError):
        CPFCipher(123)  # type: ignore[arg-type]


def test_invalid_key_error_is_value_error_subclass() -> None:
    """InvalidKeyError herda de ValueError — manter API documentada."""
    assert issubclass(InvalidKeyError, ValueError)


def test_bytearray_key_is_accepted() -> None:
    """bytearray de 32 bytes também é chave válida."""
    cipher = CPFCipher(bytearray(b"\x00" * 32))
    token = cipher.encrypt("hello")
    assert cipher.decrypt(token) == "hello"


# ---------------------------------------------------------------------------
# from_urlsafe / generate_key / generate_key_urlsafe
# ---------------------------------------------------------------------------


def test_from_urlsafe_round_trip() -> None:
    """Gerar chave urlsafe → reconstruir cipher → round-trip de plaintext."""
    key_urlsafe = CPFCipher.generate_key_urlsafe()
    cipher = CPFCipher.from_urlsafe(key_urlsafe)
    token = cipher.encrypt("12345678900")
    assert cipher.decrypt(token) == "12345678900"


def test_from_urlsafe_accepts_key_without_padding() -> None:
    """``generate_key_urlsafe`` remove ``=``; ``from_urlsafe`` deve aceitar."""
    raw = b"\x00" * 32
    key_no_pad = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    assert "=" not in key_no_pad
    cipher = CPFCipher.from_urlsafe(key_no_pad)
    token = cipher.encrypt("hello")
    assert cipher.decrypt(token) == "hello"


def test_from_urlsafe_accepts_key_with_padding() -> None:
    """``from_urlsafe`` também aceita chave com ``=`` no fim."""
    raw = b"\xab" * 32
    key_padded = base64.urlsafe_b64encode(raw).decode()
    cipher = CPFCipher.from_urlsafe(key_padded)
    token = cipher.encrypt("hello")
    assert cipher.decrypt(token) == "hello"


def test_from_urlsafe_short_raises_invalid_key_error() -> None:
    """Chave urlsafe que decodifica para !=32 bytes → InvalidKeyError."""
    short = base64.urlsafe_b64encode(b"\x00" * 16).rstrip(b"=").decode()
    with pytest.raises(InvalidKeyError):
        CPFCipher.from_urlsafe(short)


def test_generate_key_returns_32_bytes() -> None:
    key = CPFCipher.generate_key()
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_generate_key_produces_distinct_keys() -> None:
    """Sanidade do CSPRNG: 50 chaves geradas em sequência devem ser únicas."""
    keys = {CPFCipher.generate_key() for _ in range(50)}
    assert len(keys) == 50


def test_generate_key_urlsafe_decodes_to_32_bytes() -> None:
    key_urlsafe = CPFCipher.generate_key_urlsafe()
    assert isinstance(key_urlsafe, str)
    decoded = base64.urlsafe_b64decode(key_urlsafe + "==")
    assert len(decoded) == 32


def test_generate_key_urlsafe_has_no_padding() -> None:
    """Convenção: ``.env`` aceita melhor strings sem ``=``."""
    assert "=" not in CPFCipher.generate_key_urlsafe()


def test_generate_key_urlsafe_produces_distinct_keys() -> None:
    keys = {CPFCipher.generate_key_urlsafe() for _ in range(20)}
    assert len(keys) == 20


# ---------------------------------------------------------------------------
# UTF-8 / unicode
# ---------------------------------------------------------------------------


def test_encrypt_preserves_utf8_characters(cipher: CPFCipher) -> None:
    """Caracteres acentuados e ligaturas sobrevivem ao round-trip."""
    plaintext = "João Süß — Renée"
    token = cipher.encrypt(plaintext)
    assert cipher.decrypt(token) == plaintext


def test_encrypt_preserves_emoji(cipher: CPFCipher) -> None:
    """Caracteres fora do BMP (4-byte UTF-8) também sobrevivem."""
    plaintext = "👨‍⚕️ atende paciente 🩺"
    assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext


def test_encrypt_empty_string_is_round_trip_safe(cipher: CPFCipher) -> None:
    """Encriptar string vazia gera token válido com tag — docstring permite."""
    token = cipher.encrypt("")
    assert cipher.decrypt(token) == ""


# ---------------------------------------------------------------------------
# Tokens malformados
# ---------------------------------------------------------------------------


def test_decrypt_empty_token_raises_value_error(cipher: CPFCipher) -> None:
    with pytest.raises(ValueError):
        cipher.decrypt("")


def test_decrypt_short_token_raises_value_error(cipher: CPFCipher) -> None:
    """Token menor que nonce(12) + tag(16) = 28 bytes → ValueError."""
    with pytest.raises(ValueError):
        cipher.decrypt("aa")


def test_decrypt_short_token_just_below_threshold_raises_value_error(
    cipher: CPFCipher,
) -> None:
    """Boundary: 27 bytes (1 a menos que o mínimo) ainda dispara ValueError."""
    raw = b"\x00" * 27
    token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with pytest.raises(ValueError):
        cipher.decrypt(token)


# ---------------------------------------------------------------------------
# Validação de tipos
# ---------------------------------------------------------------------------


def test_encrypt_non_str_plaintext_raises_type_error(cipher: CPFCipher) -> None:
    with pytest.raises(TypeError):
        cipher.encrypt(123)  # type: ignore[arg-type]


def test_encrypt_bytes_plaintext_raises_type_error(cipher: CPFCipher) -> None:
    with pytest.raises(TypeError):
        cipher.encrypt(b"12345678900")  # type: ignore[arg-type]


def test_encrypt_none_plaintext_raises_type_error(cipher: CPFCipher) -> None:
    with pytest.raises(TypeError):
        cipher.encrypt(None)  # type: ignore[arg-type]


def test_decrypt_bytes_token_raises_type_error(cipher: CPFCipher) -> None:
    with pytest.raises(TypeError):
        cipher.decrypt(b"abc")  # type: ignore[arg-type]


def test_decrypt_none_token_raises_type_error(cipher: CPFCipher) -> None:
    with pytest.raises(TypeError):
        cipher.decrypt(None)  # type: ignore[arg-type]


def test_decrypt_int_token_raises_type_error(cipher: CPFCipher) -> None:
    with pytest.raises(TypeError):
        cipher.decrypt(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Formato do token
# ---------------------------------------------------------------------------


def test_token_is_str(cipher: CPFCipher) -> None:
    token = cipher.encrypt("12345678900")
    assert isinstance(token, str)


def test_token_has_no_padding(cipher: CPFCipher) -> None:
    """Convenção urlsafe-sem-padding mantida pelo encrypt."""
    token = cipher.encrypt("12345678900")
    assert "=" not in token


def test_token_minimum_size_is_28_bytes_raw(cipher: CPFCipher) -> None:
    """Plaintext vazio → 12 nonce + 0 ct + 16 tag = 28 bytes brutos."""
    token = cipher.encrypt("")
    raw = base64.urlsafe_b64decode(token + "==")
    assert len(raw) == CPFCipher.NONCE_BYTES + 16

"""Criptografia AES-256-GCM para PII (CPF e similares).

Stateless. Chave passada via construtor; nunca lida de env diretamente —
o caller (ex.: ``settings.CPF_ENCRYPTION_KEY``) decide a fonte. Isso desacopla
o helper das settings do Django e facilita testes unitários (S1-15).

Decisões de design
------------------
- **AES-256-GCM** (modo autenticado): protege confidencialidade *e* integridade.
  Tentativa de tampering no ciphertext gera ``InvalidTag`` na descriptografia.
  Não usamos AES-CBC (vulnerável a padding oracle) nem AES-CTR puro (sem MAC).
- **Nonce de 12 bytes** (recomendação NIST SP 800-38D para GCM). Gerado via
  ``secrets.token_bytes`` (CSPRNG) em **toda** chamada de ``encrypt`` — duas
  chamadas com o mesmo plaintext retornam tokens diferentes, comportamento
  desejado para evitar correlação no banco.
- **Formato do token**: ``base64-urlsafe(nonce || ciphertext || tag)``. URL-safe
  para facilitar logs/URLs sem precisar de escape. Padding ``=`` é removido na
  serialização e re-adicionado na deserialização.
- **AAD opcional** (Additional Authenticated Data): use para *binding contextual*
  — por exemplo, ``aad=str(paciente.id).encode()`` trava o token àquele paciente.
  Se alguém tentar mover o CPF criptografado para outro registro, a tag falha.
  AAD não é criptografada, mas faz parte do MAC.

Uso típico (após S1-7 expor ``settings.CPF_ENCRYPTION_KEY``)::

    from django.conf import settings
    from apps.core.security.crypto import CPFCipher

    cipher = CPFCipher.from_urlsafe(settings.CPF_ENCRYPTION_KEY)
    token = cipher.encrypt("12345678900", aad=str(paciente.id).encode())
    cpf = cipher.decrypt(token, aad=str(paciente.id).encode())

Geração da chave para o ``.env`` (uso pontual, não em runtime)::

    python -c "from apps.core.security.crypto import CPFCipher; \\
               print(CPFCipher.generate_key_urlsafe())"
"""

from __future__ import annotations

import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class InvalidKeyError(ValueError):
    """Chave AES inválida (deve ser 32 bytes/256 bits)."""


class CPFCipher:
    """Wrapper sobre AESGCM para criptografar/descriptografar CPF (e PII em geral).

    Formato de saída: ``base64-urlsafe(nonce || ciphertext || tag)``.
    Nonce de 12 bytes (recomendação NIST para GCM).

    A chave **deve** vir de ``settings.CPF_ENCRYPTION_KEY`` (configurada via
    django-environ — S1-7). Nunca leia env diretamente daqui: mantém o helper
    puro e testável sem precisar de Django.

    Notas de uso
    ------------
    - ``aad`` (Additional Authenticated Data) é opcional. Use-a para *binding
      contextual* — ex.: ``aad=str(paciente.id).encode()`` trava o CPF naquele
      paciente. Tampering ou troca de contexto = ``InvalidTag`` no decrypt.
    - O nonce é DIFERENTE em toda chamada de ``encrypt`` (gerado via CSPRNG).
      Encriptar o mesmo plaintext duas vezes produz tokens distintos — desejável
      para evitar correlação no banco.
    - Não chame ``encrypt`` com plaintext vazio sem motivo; o token resultante
      ainda contém nonce + tag e ocupa ~28 bytes mesmo para string vazia.
    """

    NONCE_BYTES = 12

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise InvalidKeyError("Chave AES-256 deve ter exatamente 32 bytes.")
        self._aesgcm = AESGCM(bytes(key))

    @classmethod
    def from_urlsafe(cls, key_urlsafe: str) -> CPFCipher:
        """Constrói a partir de chave base64-urlsafe (formato comum em ``.env``).

        Aceita chave com ou sem padding ``=``. Levanta ``InvalidKeyError`` se
        a chave decodificada não tiver 32 bytes.
        """
        key = base64.urlsafe_b64decode(key_urlsafe + "==")
        return cls(key)

    @staticmethod
    def generate_key() -> bytes:
        """Gera chave AES-256 aleatória (32 bytes) via CSPRNG."""
        return AESGCM.generate_key(bit_length=256)

    @staticmethod
    def generate_key_urlsafe() -> str:
        """Gera chave em formato base64-urlsafe (sem padding) para colar no ``.env``."""
        return base64.urlsafe_b64encode(CPFCipher.generate_key()).rstrip(b"=").decode()

    def encrypt(self, plaintext: str, *, aad: bytes | None = None) -> str:
        """Criptografa string UTF-8. Retorna ``base64-urlsafe(nonce || ct || tag)``.

        Parameters
        ----------
        plaintext:
            String a criptografar (geralmente CPF). Deve ser ``str`` (UTF-8).
        aad:
            Additional Authenticated Data. Não é criptografada, mas entra no MAC.
            Útil para binding contextual (ex.: ID do paciente).
        """
        if not isinstance(plaintext, str):
            raise TypeError("plaintext deve ser str.")
        nonce = secrets.token_bytes(self.NONCE_BYTES)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.urlsafe_b64encode(nonce + ct).rstrip(b"=").decode()

    def decrypt(self, token: str, *, aad: bytes | None = None) -> str:
        """Descriptografa token gerado por :meth:`encrypt`.

        Levanta ``cryptography.exceptions.InvalidTag`` se o token foi modificado
        ou se o ``aad`` informado difere do usado na encriptação. Levanta
        ``ValueError`` se o token tiver tamanho inválido.
        """
        if not isinstance(token, str):
            raise TypeError("token deve ser str.")
        raw = base64.urlsafe_b64decode(token + "==")
        if len(raw) < self.NONCE_BYTES + 16:  # nonce + GCM tag mínimo (16 bytes)
            raise ValueError("Token AES inválido (tamanho insuficiente).")
        nonce, ct = raw[: self.NONCE_BYTES], raw[self.NONCE_BYTES :]
        pt = self._aesgcm.decrypt(nonce, ct, aad)
        return pt.decode("utf-8")

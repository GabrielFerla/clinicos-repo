"""Geração de embeddings para a busca semântica de FAQ.

O modelo roda no **Ollama** (``all-minilm``, 46 MB, 384 dimensões), não em
``sentence-transformers``: essa escolha tira ``torch`` (~2,3 GB) da imagem do
Django sem mudar o modelo decidido no ADR-0004 — muda o *runtime* que o serve.
Ver ``docs/CHAT_MVP.md`` §Bloco 2.

Este módulo usa só a stdlib (``urllib``) para falar HTTP. É deliberado: a
camada de IA precisa ser importável e testável no CI sem depender de SDK, e o
endpoint ``/api/embed`` é um POST de JSON — não vale um cliente inteiro.

A invariante que este módulo protege
------------------------------------
Indexar com um modelo e consultar com outro devolve **lixo sem erro nenhum**:
o Oracle calcula ``VECTOR_DISTANCE`` entre dois vetores de 384 floats felizes
da vida, mesmo que venham de espaços vetoriais diferentes. Não há exceção, não
há aviso — só um ranking silenciosamente errado.

Por isso todo vetor que entra é conferido contra ``settings.EMBEDDING_DIM``
antes de sair daqui, e ``FaqVector`` guarda ``embedding_modelo`` /
``embedding_dim`` na linha para a consulta poder recusar o que não bate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Cold start medido: 17s para carregar o modelo de embedding na VRAM
# (``docs/CHAT_MVP.md`` §4.2). Com o modelo quente a chamada leva 20-50ms — o
# timeout largo existe só para o primeiro request depois de subir o Ollama.
TIMEOUT_PADRAO_SEGUNDOS = 60

# Esquemas aceitos na URL do provedor. Bloqueia ``file://`` e afins caso a
# variável de ambiente venha envenenada.
ESQUEMAS_PERMITIDOS = ("http", "https")

MENSAGEM_INDISPONIVEL = (
    "Não consegui consultar a base de conhecimento agora. Tente de novo em instantes."
)


class EmbeddingError(RuntimeError):
    """Base de todos os erros desta camada — permite um ``except`` só."""


class EmbeddingIndisponivelError(EmbeddingError):
    """O provedor de embeddings não respondeu (timeout, conexão, erro HTTP).

    Como em ``LLMIndisponivelError``, a mensagem é exibível ao usuário: nunca
    deve conter ``str(exc)``, URL do provedor ou caminho interno.
    """


class DimensaoEmbeddingError(EmbeddingError):
    """A dimensão recebida diverge de ``settings.EMBEDDING_DIM``.

    Erro de configuração, não de runtime: significa que ``EMBEDDING_MODEL``
    aponta para um modelo diferente do que criou a coluna ``VECTOR(384)``.
    Falhar alto aqui é o objetivo — o comportamento sem essa checagem é
    ranking errado sem sintoma nenhum.
    """


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface mínima consumida pelo repositório de FAQ e pelo reindexador."""

    def gerar(self, textos: list[str]) -> list[list[float]]:
        """Gera um vetor por texto, na mesma ordem da entrada.

        Args:
            textos: Textos a vetorizar. Lista vazia devolve lista vazia, sem
                tocar na rede.

        Returns:
            Um vetor de ``settings.EMBEDDING_DIM`` floats por texto.

        Raises:
            EmbeddingIndisponivelError: provedor fora do ar.
            DimensaoEmbeddingError: resposta com dimensão inesperada.
        """
        ...


def validar_dimensoes(
    vetores: list[list[float]],
    *,
    dim_esperada: int,
    quantidade_esperada: int,
    modelo: str,
) -> None:
    """Confere quantidade e dimensão dos vetores; levanta se algo divergir.

    Função de módulo para ser testável direto, sem provedor nem rede — é a
    guarda mais importante desta camada.

    Raises:
        DimensaoEmbeddingError: contagem ou dimensão fora do esperado.
    """
    if len(vetores) != quantidade_esperada:
        raise DimensaoEmbeddingError(
            f"O provedor devolveu {len(vetores)} vetor(es) para "
            f"{quantidade_esperada} texto(s) (modelo={modelo!r})."
        )

    for indice, vetor in enumerate(vetores):
        if len(vetor) != dim_esperada:
            raise DimensaoEmbeddingError(
                f"Embedding do texto #{indice} tem {len(vetor)} dimensões, "
                f"mas EMBEDDING_DIM={dim_esperada} (modelo={modelo!r}). "
                "Indexar com um modelo e consultar com outro devolve resultado "
                "errado sem erro nenhum — ajuste EMBEDDING_MODEL/EMBEDDING_DIM "
                "e reindexe a FAQ."
            )


class OllamaEmbeddingProvider:
    """Provedor que chama ``POST {base_url}/api/embed`` no Ollama.

    Usa o endpoint **nativo** do Ollama (``/api/embed``), não o compatível com
    a OpenAI: o nativo aceita lote (``input`` como lista) e devolve
    ``{"embeddings": [[...], ...]}`` direto, sem o envelope de ``data``.

    Args:
        base_url: Default ``settings.EMBEDDING_BASE_URL`` (sem ``/v1``).
        modelo: Default ``settings.EMBEDDING_MODEL``.
        dim: Dimensão esperada. Default ``settings.EMBEDDING_DIM``.
        timeout: Segundos. Default ``EMBEDDING_TIMEOUT_SEGUNDOS`` se existir
            nas settings, senão :data:`TIMEOUT_PADRAO_SEGUNDOS`.
        transporte: Substitui o POST HTTP (usado nos testes). Recebe o payload
            já montado e devolve o JSON decodificado.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        modelo: str | None = None,
        dim: int | None = None,
        timeout: float | None = None,
        transporte: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = (base_url or settings.EMBEDDING_BASE_URL).rstrip("/")
        self.modelo = modelo or settings.EMBEDDING_MODEL
        self.dim = dim if dim is not None else settings.EMBEDDING_DIM
        self.timeout = (
            timeout
            if timeout is not None
            else getattr(settings, "EMBEDDING_TIMEOUT_SEGUNDOS", TIMEOUT_PADRAO_SEGUNDOS)
        )
        self._transporte = transporte or self._post

        esquema = urlparse(self.base_url).scheme
        if esquema not in ESQUEMAS_PERMITIDOS:
            raise ImproperlyConfigured(
                f"EMBEDDING_BASE_URL precisa usar {' ou '.join(ESQUEMAS_PERMITIDOS)}; "
                f"veio esquema {esquema!r}."
            )

    @property
    def url(self) -> str:
        """Endpoint completo de embeddings."""
        return f"{self.base_url}/api/embed"

    def gerar(self, textos: list[str]) -> list[list[float]]:
        """Vetoriza ``textos`` em uma única chamada (o Ollama aceita lote)."""
        if not textos:
            return []

        # A tradução de erro fica aqui, e não no transporte: assim ela vale
        # para qualquer transporte injetado, e o contrato do método ("falha de
        # provedor vira EmbeddingIndisponivelError") não depende de quem faz o
        # HTTP. ``HTTPError`` herda de ``URLError``; ``JSONDecodeError``, de
        # ``ValueError`` — a tupla é explícita só para documentar a intenção.
        try:
            corpo = self._transporte({"model": self.modelo, "input": list(textos)})
            brutos = corpo.get("embeddings") if isinstance(corpo, dict) else None
            vetores = (
                [[float(valor) for valor in vetor] for vetor in brutos]
                if isinstance(brutos, list)
                else None
            )
        except (urllib.error.URLError, TimeoutError, OSError, TypeError, ValueError) as exc:
            # ``str(exc)`` traz a URL e o host — só o log recebe.
            logger.exception("Falha ao gerar embeddings (modelo=%s).", self.modelo)
            raise EmbeddingIndisponivelError(MENSAGEM_INDISPONIVEL) from exc

        if vetores is None:
            logger.error("Resposta de embedding sem a chave 'embeddings' (modelo=%s).", self.modelo)
            raise EmbeddingIndisponivelError(MENSAGEM_INDISPONIVEL)

        validar_dimensoes(
            vetores,
            dim_esperada=self.dim,
            quantidade_esperada=len(textos),
            modelo=self.modelo,
        )
        return vetores

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST de JSON via stdlib. Erros de rede sobem para :meth:`gerar`."""
        requisicao = urllib.request.Request(  # noqa: S310 — esquema validado no __init__
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(  # noqa: S310 — idem
            requisicao, timeout=self.timeout
        ) as resposta:
            return json.loads(resposta.read().decode("utf-8"))


class FakeEmbeddingProvider:
    """Provedor determinístico derivado de SHA-256 — sem rede, sem modelo.

    Serve para o CI e para rodar a aplicação sem Ollama. As propriedades que
    importam:

    - **Determinístico entre execuções.** Deriva de ``hashlib.sha256``, não de
      ``hash()`` — que é aleatorizado por processo via ``PYTHONHASHSEED`` e
      produziria vetores diferentes a cada run.
    - **Dimensão correta**, igual a ``settings.EMBEDDING_DIM``, para exercitar
      a mesma validação do provedor real.
    - **Normalizado L2** (norma 1), como os embeddings de verdade — a distância
      cosseno do Oracle assume isso.

    Não tem nenhuma semântica: textos parecidos geram vetores tão distantes
    quanto textos diferentes. Serve para testar encanamento, jamais relevância
    (que é ``@pytest.mark.oracle``, contra o modelo real).
    """

    # 4 bytes por float: consome o hash em blocos de 32 bytes e reexpande.
    BYTES_POR_FLOAT = 4

    def __init__(self, *, dim: int | None = None, modelo: str = "fake-embedding") -> None:
        self.dim = dim if dim is not None else settings.EMBEDDING_DIM
        self.modelo = modelo

    def gerar(self, textos: list[str]) -> list[list[float]]:
        """Gera um vetor determinístico por texto."""
        return [self._vetor(texto) for texto in textos]

    def _vetor(self, texto: str) -> list[float]:
        crus = self._bytes_deterministicos(texto, self.dim * self.BYTES_POR_FLOAT)

        valores: list[float] = []
        for inicio in range(0, len(crus), self.BYTES_POR_FLOAT):
            bloco = crus[inicio : inicio + self.BYTES_POR_FLOAT]
            # inteiro de 32 bits → [0, 1) → [-1, 1)
            valores.append(int.from_bytes(bloco, "big") / 2**32 * 2 - 1)

        return self._normalizar(valores)

    @staticmethod
    def _bytes_deterministicos(texto: str, quantidade: int) -> bytes:
        """Expande SHA-256 (32 bytes) até ``quantidade`` bytes, em contador.

        384 floats pedem 1536 bytes — 48 digests. O contador entra no material
        hasheado para cada bloco sair diferente do anterior.
        """
        semente = texto.encode("utf-8")
        saida = bytearray()
        bloco = 0
        while len(saida) < quantidade:
            saida += hashlib.sha256(semente + b"::" + str(bloco).encode("ascii")).digest()
            bloco += 1
        return bytes(saida[:quantidade])

    @staticmethod
    def _normalizar(valores: list[float]) -> list[float]:
        """Normaliza L2. Vetor nulo (improvável) vira o versor do eixo 0."""
        norma = math.sqrt(sum(valor * valor for valor in valores))
        if norma == 0:
            nulo = [0.0] * len(valores)
            if nulo:
                nulo[0] = 1.0
            return nulo
        return [valor / norma for valor in valores]


PROVEDORES: dict[str, type] = {
    "ollama": OllamaEmbeddingProvider,
    "fake": FakeEmbeddingProvider,
}


def get_embedding_provider() -> EmbeddingProvider:
    """Instancia o provedor configurado em ``settings.EMBEDDING_PROVIDER``.

    Raises:
        ImproperlyConfigured: provedor desconhecido.
    """
    nome = str(getattr(settings, "EMBEDDING_PROVIDER", "") or "").strip().lower()

    try:
        classe = PROVEDORES[nome]
    except KeyError:
        validos = ", ".join(sorted(PROVEDORES))
        raise ImproperlyConfigured(
            f"EMBEDDING_PROVIDER={nome!r} não é um provedor conhecido. Use um de: {validos}."
        ) from None

    return classe()

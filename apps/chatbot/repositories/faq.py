"""Acesso à coluna vetorial de ``FAQ_VECTOR``.

Este é o **único** ponto do ClinicOS que fala com o tipo ``VECTOR`` do Oracle
23ai. O isolamento é proposital: a coluna não existe no model (ver
``apps/chatbot/migrations/0002_faq_vector_embedding.py``), o bind exige um
caminho fora do ORM, e nada disso deve contaminar services e views.

Por que o cursor cru do driver
------------------------------
O ``oracledb`` mapeia ``array.array("f", ...)`` para ``DB_TYPE_VECTOR``
nativamente — mas só quando recebe o valor direto. O cursor do Django embrulha
cada parâmetro em ``OracleParam``, que não sabe lidar com o tipo. Medido neste
ambiente::

    cursor do Django  -> TypeError: unhashable type: 'array.array'
    cursor do driver  -> (0.0,)   # distância de um vetor para ele mesmo

Por isso ``connection.connection.cursor()``: é o cursor do ``oracledb``, sem a
camada do Django no meio. Sempre via :func:`_cursor_driver`, que garante que a
conexão esteja aberta antes (``connection.connection`` é ``None`` até o Django
conectar pela primeira vez).

Por que devolve só ``(id, distância)``
--------------------------------------
Hidratar pelo ORM depois custa uma query barata por chave primária e evita ler
``RESPOSTA`` pelo cursor cru — a coluna é NCLOB e o driver devolveria um objeto
LOB, não ``str``. De quebra, a superfície do repositório fica minúscula, o que
torna trivial fakeá-lo nos testes que rodam em SQLite.
"""

from __future__ import annotations

import array
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import connection

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Menor distância = mais similar. COSINE porque é a métrica com que os vetores
# foram indexados (ver a DDL do índice em 0003_faq_vector_indice_hnsw).
SQL_BUSCA_SEMANTICA = """
    SELECT ID, VECTOR_DISTANCE(EMBEDDING, :consulta, COSINE) AS DIST
      FROM FAQ_VECTOR
     WHERE ATIVO = 1
       AND EMBEDDING IS NOT NULL
       AND EMBEDDING_MODELO = :modelo
     ORDER BY DIST
     FETCH FIRST :limite ROWS ONLY
"""

SQL_GRAVAR_EMBEDDING = """
    UPDATE FAQ_VECTOR
       SET EMBEDDING = :vetor
     WHERE ID = :faq_id
"""


class VetorIncompativelError(ValueError):
    """O vetor não tem a dimensão declarada em ``settings.EMBEDDING_DIM``.

    Gravar um vetor de dimensão errada é rejeitado pelo Oracle (``ORA-51803``),
    mas a checagem local dá uma mensagem entendível e evita a ida ao banco.
    """


@contextmanager
def _cursor_driver() -> Iterator:
    """Entrega um cursor do ``oracledb``, sem o wrapper do Django.

    ``connection.connection`` só existe depois que o Django abriu a conexão;
    ``ensure_connection()`` cobre o caso de este ser o primeiro acesso ao banco
    no processo.
    """
    connection.ensure_connection()
    cursor = connection.connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _para_vetor_oracle(embedding: list[float]) -> array.array:
    """Converte a lista de floats no tipo que o ``oracledb`` reconhece.

    ``array.array("f", ...)`` é FLOAT32 — a mesma precisão declarada na coluna
    ``VECTOR(384, FLOAT32)``.

    Raises:
        VetorIncompativelError: se a dimensão não bate com ``EMBEDDING_DIM``.
    """
    esperado = settings.EMBEDDING_DIM
    if len(embedding) != esperado:
        raise VetorIncompativelError(
            f"Embedding com {len(embedding)} dimensões, esperado {esperado}. "
            "Provavelmente o modelo de embedding mudou sem reindexar o FAQ."
        )
    return array.array("f", (float(v) for v in embedding))


class FAQRepository:
    """Busca e escrita de embeddings na tabela ``FAQ_VECTOR``."""

    @staticmethod
    def buscar_semantica(embedding: list[float], top_k: int = 3) -> list[tuple[int, float]]:
        """Retorna os FAQs mais próximos da pergunta, por distância de cosseno.

        Args:
            embedding: Vetor da pergunta do usuário, já normalizado.
            top_k: Quantos resultados trazer.

        Returns:
            Lista de ``(faq_id, distancia)`` em ordem crescente de distância —
            o primeiro é o mais similar. Vazia se não houver FAQ indexado com o
            modelo de embedding atual.

        Raises:
            VetorIncompativelError: dimensão divergente de ``EMBEDDING_DIM``.

        A query filtra por ``EMBEDDING_MODELO``. Sem esse filtro, uma base com
        vetores de modelos diferentes devolveria um ranking silenciosamente
        errado — o Oracle calcula distância entre dois vetores de 384 floats
        sem reclamar, mesmo vindos de espaços vetoriais distintos.
        """
        vetor = _para_vetor_oracle(embedding)
        with _cursor_driver() as cursor:
            cursor.execute(
                SQL_BUSCA_SEMANTICA,
                consulta=vetor,
                modelo=settings.EMBEDDING_MODEL,
                limite=top_k,
            )
            return [(int(faq_id), float(dist)) for faq_id, dist in cursor.fetchall()]

    @staticmethod
    def gravar_embedding(faq_id: int, embedding: list[float]) -> None:
        """Grava o vetor de um FAQ.

        Os metadados (``embedding_modelo``, ``embedding_dim``,
        ``embedding_gerado_em``) são responsabilidade do chamador, via ORM, na
        mesma transação — ver o command ``reindexar_faq``.

        **Não comita.** Apesar de usar o cursor do driver, a escrita acontece na
        mesma sessão do Django, então quem controla a transação é o chamador.
        Um ``connection.commit()`` aqui dentro quebraria com
        ``TransactionManagementError`` sempre que houvesse um ``atomic()`` em
        volta — que é justamente o caso onde esta função deve ser usada, para o
        vetor e os metadados caírem juntos.

        Raises:
            VetorIncompativelError: dimensão divergente de ``EMBEDDING_DIM``.
        """
        vetor = _para_vetor_oracle(embedding)
        with _cursor_driver() as cursor:
            cursor.execute(SQL_GRAVAR_EMBEDDING, vetor=vetor, faq_id=faq_id)

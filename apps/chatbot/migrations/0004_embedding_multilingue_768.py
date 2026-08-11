"""Troca a dimensão do vetor de 384 para 768 — modelo de embedding multilíngue.

Motivo
------
O ``all-minilm`` (all-MiniLM-L6-v2) é treinado em inglês. Medido contra a FAQ
da clínica, ele casa por **sobreposição lexical** em português, não por
semântica::

    "que horas vocês abrem?"  -> "Vocês atendem pelo SUS?"      (compartilha "Vocês")
    "horário de atendimento"  -> "Vocês aceitam convênio?"

Só a paráfrase quase literal funcionava. Numa baseline de 8 perguntas escritas
como um paciente escreveria, o placar foi:

===========================  =====
``all-minilm`` (384d)        6/8
``paraphrase-multilingual``  **8/8**
===========================  =====

Como a busca semântica é o diferencial do projeto, 6/8 em paráfrase não serve.
O modelo multilíngue produz 768 dimensões, daí esta migration.

Por que dropar e recriar em vez de ``MODIFY``
---------------------------------------------
Mudar a dimensão invalida todo vetor já gravado — eles vivem em outro espaço
vetorial e não são convertíveis. Como os dados serão regerados de qualquer
forma por ``reindexar_faq``, dropar a coluna é mais honesto (e mais simples)
do que um ``ALTER`` que deixaria lixo indexável para trás.

O índice precisa cair antes da coluna e ser recriado depois, com a nova
dimensão.

**Depois desta migration, rode ``python manage.py reindexar_faq``.** Até lá a
busca não devolve nada: ``EMBEDDING`` está nulo e a query filtra por
``EMBEDDING IS NOT NULL``. O ``precisa_reindexar`` do model detecta a troca
sozinho, comparando ``embedding_dim``/``embedding_modelo`` com o settings.
"""

from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

NOME_INDICE = "IDX_FAQ_EMBEDDING"


def _executar_tolerante(schema_editor, ddl: str, descricao: str) -> None:
    """Executa DDL registrando falha em vez de abortar a migration.

    Usado só no índice, que é otimização: ver a justificativa da cascata em
    ``0003_faq_vector_indice_hnsw``.
    """
    try:
        schema_editor.execute(ddl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s falhou: %s", descricao, exc)


def _recriar(schema_editor, dimensao: int) -> None:
    """Dropa índice e coluna, recria ambos com a dimensão indicada."""
    _executar_tolerante(schema_editor, f"DROP INDEX {NOME_INDICE}", "drop do índice vetorial")
    schema_editor.execute('ALTER TABLE "FAQ_VECTOR" DROP COLUMN "EMBEDDING"')
    schema_editor.execute(
        f'ALTER TABLE "FAQ_VECTOR" ADD ("EMBEDDING" VECTOR({dimensao}, FLOAT32))'
    )
    for rotulo, organizacao in (
        ("HNSW", "INMEMORY NEIGHBOR GRAPH"),
        ("IVF", "NEIGHBOR PARTITIONS"),
    ):
        try:
            schema_editor.execute(
                f'CREATE VECTOR INDEX {NOME_INDICE} ON "FAQ_VECTOR" ("EMBEDDING") '
                f"ORGANIZATION {organizacao} DISTANCE COSINE WITH TARGET ACCURACY 95"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Índice %s falhou: %s", rotulo, exc)
            continue
        logger.info("Índice vetorial recriado (%s, %dd).", rotulo, dimensao)
        return
    logger.warning("Nenhum índice vetorial criado; a busca segue correta por full scan.")


def para_768(apps, schema_editor) -> None:
    """Aplica a nova dimensão e zera os metadados de indexação."""
    if schema_editor.connection.vendor != "oracle":
        return
    _recriar(schema_editor, 768)
    _limpar_metadados(apps)


def para_384(apps, schema_editor) -> None:
    """Rollback para a dimensão anterior."""
    if schema_editor.connection.vendor != "oracle":
        return
    _recriar(schema_editor, 384)
    _limpar_metadados(apps)


def _limpar_metadados(apps) -> None:
    """Marca todos os FAQs como não indexados.

    Sem isso, ``precisa_reindexar`` continuaria vendo a dimensão antiga
    gravada na linha e o comando pularia FAQs cujo vetor acabou de sumir.
    """
    FaqVector = apps.get_model("chatbot", "FaqVector")
    FaqVector.objects.update(embedding_gerado_em=None, embedding_modelo="", embedding_dim=None)


class Migration(migrations.Migration):
    # DDL no Oracle não roda dentro de atomic block — ver nota em 0002.
    atomic = False

    dependencies = [("chatbot", "0003_faq_vector_indice_hnsw")]

    operations = [migrations.RunPython(para_768, para_384)]

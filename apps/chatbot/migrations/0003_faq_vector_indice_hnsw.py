"""Cria o índice vetorial em ``FAQ_VECTOR.EMBEDDING`` — tarefa S1-12.

Estratégia: HNSW, com degradação em cascata
-------------------------------------------
O Oracle 23ai tem duas famílias de índice vetorial:

- **HNSW** (``ORGANIZATION INMEMORY NEIGHBOR GRAPH``) — em memória. É a
  escolha: no spike mediu 0,22 ms p50 contra 0,47 ms do full scan.
- **IVF** (``ORGANIZATION NEIGHBOR PARTITIONS``) — persistente em disco. No
  volume do spike ficou indistinguível do full scan, mas serve de rede.

HNSW exige ``vector_memory_size > 0``. A imagem ``gvenzl/oracle-free:23-slim``
sobe com esse parâmetro em 0, e ele só aceita ``SCOPE=SPFILE`` — ou seja, vale
apenas no próximo startup. ``infra/oracle-init/01_vector_memory.sql`` grava
512M e ``infra/scripts/bootstrap.sh`` faz o restart. Se alguém subir a stack
sem passar por aí, a criação falha com ``ORA-51962``.

Por isso a cascata: HNSW → IVF → segue sem índice, apenas avisando.

**O índice é performance, nunca correção.** ``VECTOR_DISTANCE`` funciona sem
ele (full scan), então uma demo não pode quebrar por causa disto. Falhar a
migration aqui seria transformar uma otimização em bloqueador.
"""

from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

NOME_INDICE = "IDX_FAQ_EMBEDDING"

CRIAR_HNSW = f"""
    CREATE VECTOR INDEX {NOME_INDICE} ON "FAQ_VECTOR" ("EMBEDDING")
    ORGANIZATION INMEMORY NEIGHBOR GRAPH
    DISTANCE COSINE
    WITH TARGET ACCURACY 95
"""

CRIAR_IVF = f"""
    CREATE VECTOR INDEX {NOME_INDICE} ON "FAQ_VECTOR" ("EMBEDDING")
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95
"""

REMOVER = f"DROP INDEX {NOME_INDICE}"


def criar_indice(apps, schema_editor) -> None:
    """Cria o índice vetorial, degradando de HNSW para IVF e depois para nada."""
    if schema_editor.connection.vendor != "oracle":
        return

    for rotulo, ddl in (("HNSW", CRIAR_HNSW), ("IVF", CRIAR_IVF)):
        try:
            schema_editor.execute(ddl)
        except Exception as exc:  # noqa: BLE001 — a intenção é justamente degradar
            logger.warning("Índice vetorial %s falhou em %s: %s", rotulo, NOME_INDICE, exc)
            continue
        logger.info("Índice vetorial %s criado (%s).", NOME_INDICE, rotulo)
        return

    logger.warning(
        "Nenhum índice vetorial pôde ser criado em %s. A busca semântica segue "
        "correta via full scan, apenas mais lenta. Verifique vector_memory_size "
        "(esperado 512M) — ver infra/scripts/bootstrap.sh.",
        NOME_INDICE,
    )


def remover_indice(apps, schema_editor) -> None:
    """Rollback. Tolera índice ausente, já que a criação é best-effort."""
    if schema_editor.connection.vendor != "oracle":
        return
    try:
        schema_editor.execute(REMOVER)
    except Exception as exc:  # noqa: BLE001 — ORA-01418: índice não existe
        logger.warning("Não foi possível remover %s: %s", NOME_INDICE, exc)


class Migration(migrations.Migration):
    # Ver a nota em 0002: DDL no Oracle não roda dentro de atomic block.
    atomic = False

    dependencies = [("chatbot", "0002_faq_vector_embedding")]

    operations = [migrations.RunPython(criar_indice, remover_indice)]

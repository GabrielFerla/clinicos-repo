"""Adiciona a coluna ``EMBEDDING VECTOR(384, FLOAT32)`` em ``FAQ_VECTOR``.

Por que fora do model
---------------------
O ORM do Django não conhece o tipo ``VECTOR`` do Oracle 23ai. Em vez de
escrever um ``Field`` custom, a coluna entra por migration e é lida/escrita
por SQL cru em ``apps/chatbot/repositories/faq.py`` — que é o padrão que
``docs/ARQUITETURA.md`` já prescreve para query complexa.

Isso é deliberado e tem três consequências boas:

- ``makemigrations`` não tenta remover a coluna, porque não a conhece: ele
  compara os models com o estado das migrations, nunca com o banco.
- O CI roda em SQLite. Como a operação é guardada por vendor, lá a tabela
  nasce sem ``EMBEDDING`` e todo teste de model, admin e tool roda normalmente.
- O rollback é literal e auditável, como exige o ``CONTRIBUTING.md``.

Um ``Field`` custom não compraria nada: o único uso do vetor é
``VECTOR_DISTANCE`` dentro de ``ORDER BY``, que não tem expressão no ORM — a
query seguiria sendo SQL cru de qualquer forma.

Sobre a dimensão
----------------
384 é **literal**, não vem de ``settings.EMBEDDING_DIM``. Migration que lê
settings faz o estado do schema virar função do ambiente: a mesma migration
produziria colunas diferentes em máquinas diferentes. O valor vem do ADR-0004
e precisa ser fixo — o índice vetorial exige dimensão declarada.

A coluna é **nullable** de propósito: a linha do FAQ é criada antes de existir
embedding, e o ``reindexar_faq`` preenche depois.
"""

from __future__ import annotations

from django.db import migrations

ADICIONAR = 'ALTER TABLE "FAQ_VECTOR" ADD ("EMBEDDING" VECTOR(384, FLOAT32))'
REMOVER = 'ALTER TABLE "FAQ_VECTOR" DROP COLUMN "EMBEDDING"'


def _somente_oracle(schema_editor) -> bool:
    """Indica se o backend atual suporta o tipo ``VECTOR``.

    Guardar por vendor é o que mantém a suíte rodando em SQLite. Um
    ``migrations.RunSQL`` puro seria executado em qualquer backend e quebraria
    o CI na hora.
    """
    return schema_editor.connection.vendor == "oracle"


def adicionar_coluna(apps, schema_editor) -> None:
    """Cria a coluna vetorial (no-op fora do Oracle)."""
    if _somente_oracle(schema_editor):
        schema_editor.execute(ADICIONAR)


def remover_coluna(apps, schema_editor) -> None:
    """Rollback: remove a coluna vetorial (no-op fora do Oracle)."""
    if _somente_oracle(schema_editor):
        schema_editor.execute(REMOVER)


class Migration(migrations.Migration):
    # DDL fora de transação. O Django envolve `RunPython` num atomic block por
    # padrão, e aí o `schema_editor` recusa executar DDL num backend que não
    # faz rollback dele — `TransactionManagementError`. O Oracle comita DDL
    # implicitamente, então o atomic block seria ilusório de qualquer forma.
    atomic = False

    dependencies = [("chatbot", "0001_initial")]

    operations = [migrations.RunPython(adicionar_coluna, remover_coluna)]

"""Cria o trigger de imutabilidade de ``EVOLUCAO`` — tarefa S1-10.

O DDL é o que a ``docs/ARQUITETURA.md`` prescreve em "Imutabilidade do
prontuário": ``BEFORE UPDATE OR DELETE``, ``FOR EACH ROW``, levantando
``ORA-20001``. A justificativa de pôr a regra no banco, e não em ``save()``,
está lá: o CFM exige prontuário não-alterável, e no banco nem um bug grave da
aplicação, nem um SQL fora do ORM, nem uma injeção conseguem corromper o
registro.

Isto **não** é o 0003 do chatbot — não copie o try/except de lá
------------------------------------------------------------------
``chatbot/migrations/0003_faq_vector_indice_hnsw.py`` tem a mesma forma
(``RunPython`` + ``atomic = False`` + guarda de vendor) e engole a exceção de
propósito: índice vetorial é **performance**, a busca continua correta via full
scan, e derrubar a migration por causa de uma otimização seria transformar
melhoria em bloqueador.

Aqui é o oposto exato. O trigger é **conformidade CFM**: sem ele, ``EVOLUCAO``
é uma tabela comum que aceita ``UPDATE`` e ``DELETE``, e o sistema passa a
violar a exigência legal *em silêncio* — que é a pior falha possível, porque
ninguém descobre até auditoria ou processo. Por isso não há ``try/except`` na
criação: se o ``CREATE TRIGGER`` falhar, a migration falha alto e o deploy para.
Quem for "uniformizar" os dois arquivos um dia: eles são diferentes de
propósito, e a diferença é esta.

Executar PL/SQL pelo ``python-oracledb``
----------------------------------------
O ``/`` no fim do bloco é terminador do **SQL*Plus**, não do driver — mandá-lo
para o ``execute()`` dá ``ORA-00911: invalid character``. Só que o corpo do
trigger *precisa* terminar em ``END;`` com o ponto e vírgula, e o cursor Oracle
do Django (``FormatStylePlaceholderCursor._fix_for_params``) remove o último
caractere quando ele é ``;`` **ou** ``/`` — o que decapitaria justamente esse
``END;``.

A saída é a que o próprio Django documenta no comentário daquele método:
manter o ``/`` como último caractere da string. O Django o remove, o driver
recebe ``... END;`` íntegro, e o bloco compila. Consequência prática: a
constante abaixo **não pode** ganhar quebra de linha ou espaço depois do ``/``
— com qualquer coisa após ele o ``endswith`` do Django falha, o ``/`` viaja
para o banco e a migration morre em ``ORA-00911``.
"""

from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

NOME_TRIGGER = "TRG_EVOLUCAO_IMUTAVEL"

# A string termina exatamente em "/" (ver docstring). Não acrescente nada
# depois dele — nem newline.
CRIAR_TRIGGER = f"""
CREATE OR REPLACE TRIGGER {NOME_TRIGGER}
BEFORE UPDATE OR DELETE ON EVOLUCAO
FOR EACH ROW
BEGIN
    RAISE_APPLICATION_ERROR(-20001,
        'EVOLUCAO é append-only por exigência do CFM. Use nova evolução com referência à anterior.');
END;
/"""

REMOVER_TRIGGER = f"DROP TRIGGER {NOME_TRIGGER}"

# Um CREATE que "passa" mas compila com erro deixa o trigger INVALID, e trigger
# inválido não protege nada. ORA-24344 costuma vir como exceção, mas a checagem
# explícita é barata e fecha a única brecha silenciosa que sobra.
CONFERIR_TRIGGER = f"""
SELECT t.STATUS, o.STATUS
FROM USER_TRIGGERS t
JOIN USER_OBJECTS o
  ON o.OBJECT_NAME = t.TRIGGER_NAME AND o.OBJECT_TYPE = 'TRIGGER'
WHERE t.TRIGGER_NAME = '{NOME_TRIGGER}'
"""


def criar_trigger(apps, schema_editor) -> None:
    """Cria o trigger. **Falha alto** em qualquer erro — ver docstring do módulo."""
    if schema_editor.connection.vendor != "oracle":
        # SQLite (testes) não tem PL/SQL. Lá a imutabilidade não existe, e é por
        # isso que o teste do trigger é ``@pytest.mark.oracle``.
        return

    schema_editor.execute(CRIAR_TRIGGER, params=None)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(CONFERIR_TRIGGER)
        linha = cursor.fetchone()

    if linha is None:
        raise RuntimeError(
            f"{NOME_TRIGGER} não existe depois do CREATE. Sem ele EVOLUCAO aceita "
            "UPDATE/DELETE e o sistema viola a exigência de imutabilidade do CFM."
        )
    habilitado, validade = linha
    if habilitado != "ENABLED" or validade != "VALID":
        raise RuntimeError(
            f"{NOME_TRIGGER} foi criado mas está {habilitado}/{validade} (esperado "
            "ENABLED/VALID). Trigger desabilitado ou inválido não impede UPDATE nem "
            "DELETE. Investigue com: SELECT * FROM USER_ERRORS WHERE NAME = "
            f"'{NOME_TRIGGER}'."
        )
    logger.info("Trigger de imutabilidade %s criado e válido.", NOME_TRIGGER)


def remover_trigger(apps, schema_editor) -> None:
    """Rollback. Tolera trigger ausente (``ORA-04080``) para não travar um
    ``migrate prontuario zero`` parcial ou repetido."""
    if schema_editor.connection.vendor != "oracle":
        return
    try:
        schema_editor.execute(REMOVER_TRIGGER, params=None)
    except Exception as exc:  # noqa: BLE001 — ORA-04080: trigger não existe
        logger.warning("Não foi possível remover %s: %s", NOME_TRIGGER, exc)


class Migration(migrations.Migration):
    # DDL no Oracle faz commit implícito e não roda dentro de atomic block —
    # mesma razão das migrations 0002/0003 do chatbot.
    atomic = False

    dependencies = [("prontuario", "0001_initial")]

    operations = [migrations.RunPython(criar_trigger, remover_trigger)]

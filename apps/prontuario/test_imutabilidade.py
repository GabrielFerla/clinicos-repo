"""Testes do trigger de imutabilidade de ``EVOLUCAO`` `[S1-10]` — exigem Oracle real.

Este é o teste que fecha o item "Trigger de imutabilidade testado: ``UPDATE``
em ``EVOLUCAO`` lança exceção" do Definition of Done da Sprint 1, e é a demo
nº 3 da review. A garantia que ele verifica é de **conformidade CFM**, não de
performance: sem o trigger, ``EVOLUCAO`` vira tabela comum e o prontuário passa
a ser alterável em silêncio.

Não há como fingir isto em SQLite — ``RAISE_APPLICATION_ERROR`` é PL/SQL. Por
isso o marker ``oracle`` (auto-pulado fora do ambiente com Oracle, ver
``conftest.py`` da raiz). Rode com ``make test-oracle``.

Por que o teste escreve na base de desenvolvimento — e mesmo assim não suja nada
------------------------------------------------------------------------------
``test_faq_repository.py`` explica por que não há banco de teste no Oracle: o
usuário ``clinicos`` não tem privilégio para criar outro usuário, e conceder
DBA só para rodar teste seria pior. Lá a contrapartida era "nenhum teste
escreve". Aqui escrever é inevitável — só se testa um trigger de ``UPDATE``
tendo uma linha para atualizar.

A saída é a transação: tudo nasce dentro de um ``atomic`` que termina em
``set_rollback(True)``. E o detalhe que faz isso funcionar justamente nesta
tabela: ``ROLLBACK`` **não** é ``DELETE``. O trigger é ``BEFORE UPDATE OR
DELETE``, então ele não é disparado por um rollback — o que seria um beco sem
saída, já que uma linha de ``EVOLUCAO`` inserida de verdade nunca mais poderia
ser removida.

As asserções são sobre ``ORA-20001``, o código que a ``ARQUITETURA.md``
prescreve, e não sobre o texto da mensagem — mensagem se traduz, código de erro
é contrato.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import DatabaseError, transaction

from apps.crm.models import Medico, Paciente
from apps.prontuario.models import Evolucao, Prontuario

pytestmark = pytest.mark.oracle

TEXTO_ORIGINAL = "Pressão intraocular 14 mmHg em ambos os olhos."


@pytest.fixture
def evolucao(django_db_blocker):
    """Cria paciente → prontuário → evolução e desfaz tudo no fim (ver docstring)."""
    with django_db_blocker.unblock(), transaction.atomic():
        paciente = Paciente(
            nome="Paciente de Teste S1-10",
            data_nascimento=dt.date(1980, 5, 3),
        )
        paciente.definir_cpf("00000000191")
        paciente.save()

        medico = Medico.objects.create(
            nome="Médico de Teste S1-10", crm_numero="S110TEST", crm_uf="SP"
        )
        prontuario = Prontuario.objects.create(paciente=paciente)

        yield Evolucao.objects.create(prontuario=prontuario, medico=medico, texto=TEXTO_ORIGINAL)

        # Desfaz o cenário inteiro. Não é DELETE, então o trigger não reage.
        transaction.set_rollback(True)


def test_insert_continua_funcionando_com_o_trigger_ativo(evolucao: Evolucao) -> None:
    """Append-only não é read-only: o trigger é BEFORE UPDATE OR DELETE, e
    escrever novas evoluções é o funcionamento normal do prontuário."""
    assert evolucao.pk is not None
    assert Evolucao.objects.filter(pk=evolucao.pk).exists()

    with transaction.atomic():
        outra = Evolucao.objects.create(
            prontuario=evolucao.prontuario,
            medico=evolucao.medico,
            texto="Retorno: sem alterações.",
            evolucao_anterior=evolucao,
        )
    assert outra.pk != evolucao.pk


def test_update_em_evolucao_e_recusado_pelo_banco(evolucao: Evolucao) -> None:
    """O item do Definition of Done da Sprint 1."""
    with pytest.raises(DatabaseError) as erro, transaction.atomic():
        Evolucao.objects.filter(pk=evolucao.pk).update(texto="texto adulterado")

    assert "ORA-20001" in str(erro.value)


def test_update_pelo_save_do_orm_tambem_e_recusado(evolucao: Evolucao) -> None:
    """O caminho que um bug da aplicação usaria sem perceber."""
    evolucao.texto = "texto adulterado pelo ORM"

    with pytest.raises(DatabaseError) as erro, transaction.atomic():
        evolucao.save(update_fields=["texto"])

    assert "ORA-20001" in str(erro.value)


def test_delete_em_evolucao_e_recusado_pelo_banco(evolucao: Evolucao) -> None:
    with pytest.raises(DatabaseError) as erro, transaction.atomic():
        Evolucao.objects.filter(pk=evolucao.pk).delete()

    assert "ORA-20001" in str(erro.value)


def test_o_texto_original_permanece_intacto(evolucao: Evolucao) -> None:
    """Fecha o ciclo: depois das tentativas recusadas, o registro é o mesmo."""
    for tentativa in (
        lambda: Evolucao.objects.filter(pk=evolucao.pk).update(texto="adulterado"),
        lambda: Evolucao.objects.filter(pk=evolucao.pk).delete(),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            tentativa()

    do_banco = Evolucao.objects.get(pk=evolucao.pk)
    assert do_banco.texto == TEXTO_ORIGINAL
    assert do_banco.conteudo_hash == evolucao.conteudo_hash

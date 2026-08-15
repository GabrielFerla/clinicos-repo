"""Testes do ``AgendamentoService`` `[S3-6]` `[S3-7]` `[S3-8]`.

O que se verifica aqui é **contrato**: qual exceção sai em cada recusa, qual
estado fica no banco depois, e que nenhuma falha deixa lixo. Rodam em SQLite,
como o resto da suíte padrão.

Uma armadilha explícita, para ninguém ler resultado verde a mais do que ele
diz: em SQLite o ``select_for_update()`` do service é **no-op**. O backend não
suporta lock de linha, então o Django omite a cláusula em silêncio — sem erro,
sem aviso. Logo, nada neste arquivo prova que o lock funciona; ele prova que o
service se comporta corretamente *dado* que a corrida aconteceu. O lock de
verdade e a constraint no schema são exercidos em
``test_agendamento_oracle.py``, sob ``@pytest.mark.oracle``.

A corrida é simulada sem thread nem segundo processo: cria-se a ``Consulta``
concorrente direto pelo ORM **deixando o slot ``LIVRE``**, que é exatamente o
estado que a transação perdedora enxerga entre a checagem de status e o
``INSERT``. Determinístico e sem sleep — teste de concorrência com thread e
timing é o tipo de teste que fica intermitente e acaba desabilitado.
"""

from __future__ import annotations

import datetime as dt
import inspect

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agenda.models import AgendaSlot, Consulta
from apps.agenda.services.agendamento import (
    AgendamentoError,
    AgendamentoService,
    SlotIndisponivelError,
    SlotNoPassadoError,
)
from apps.crm.models import Medico, Paciente

pytestmark = pytest.mark.django_db

# Datas relativas ao dia da execução: o service compara com
# ``timezone.localdate()``, então data fixa faria o teste do "slot no passado"
# passar por acaso hoje e falhar (ou pior, virar verde falso) daqui a um ano.
HOJE = timezone.localdate()
AMANHA = HOJE + dt.timedelta(days=1)
ONTEM = HOJE - dt.timedelta(days=1)

NOVE_HORAS = dt.time(9, 0)
NOVE_E_MEIA = dt.time(9, 30)


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


@pytest.fixture
def joana() -> Paciente:
    return _paciente()


def _paciente(nome: str = "Joana Prado", cpf: str = "12345678909") -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=dt.date(1980, 5, 17))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


def _slot(medico: Medico, **overrides: object) -> AgendaSlot:
    dados: dict[str, object] = {
        "medico": medico,
        "data": AMANHA,
        "hora_inicio": NOVE_HORAS,
        "hora_fim": NOVE_E_MEIA,
    }
    dados.update(overrides)
    return AgendaSlot.objects.create(**dados)


# ---------------------------------------------------------------------------
# Caminho feliz [S3-7]
# ---------------------------------------------------------------------------


def test_slot_livre_vira_consulta_e_slot_reservado(medica: Medico, joana: Paciente) -> None:
    slot = _slot(medica)

    consulta = AgendamentoService.agendar(
        paciente=joana,
        slot_id=slot.pk,
        origem=Consulta.Origem.CHAT,
        observacoes="paciente prefere chegar mais cedo",
    )

    assert consulta.pk is not None
    assert consulta.paciente == joana
    assert consulta.slot == slot
    assert consulta.status == Consulta.Status.AGENDADA
    assert consulta.origem == Consulta.Origem.CHAT
    assert consulta.observacoes == "paciente prefere chegar mais cedo"

    slot.refresh_from_db()
    assert slot.status == AgendaSlot.Status.RESERVADO


def test_medico_da_consulta_vem_do_slot(medica: Medico, joana: Paciente) -> None:
    """A invariante que o banco não impõe e o service é responsável por manter."""
    slot = _slot(medica)

    consulta = AgendamentoService.agendar(
        paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.RECEPCAO
    )

    assert consulta.medico == slot.medico
    assert consulta.medico == medica


def test_agendar_nao_aceita_medico_do_caller() -> None:
    """Contrato de assinatura: "nenhum caller deve informar o médico à mão"."""
    parametros = inspect.signature(AgendamentoService.agendar).parameters

    assert "medico" not in parametros
    # Tudo keyword-only: `agendar(joana, 12)` não compila, então não há como
    # trocar paciente por slot na ordem dos argumentos.
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parametros.values())


def test_origem_e_obrigatoria() -> None:
    """Sem default: ``origem`` é o denominador da métrica de conversão [S5-28]."""
    origem = inspect.signature(AgendamentoService.agendar).parameters["origem"]
    assert origem.default is inspect.Parameter.empty


def test_slot_de_hoje_e_aceito(medica: Medico, joana: Paciente) -> None:
    """Borda da regra de data: "anterior a hoje" exclui hoje."""
    slot = _slot(medica, data=HOJE)

    consulta = AgendamentoService.agendar(
        paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.SITE
    )

    assert consulta.slot.data == HOJE


# ---------------------------------------------------------------------------
# Recusas [S3-7]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [AgendaSlot.Status.RESERVADO, AgendaSlot.Status.BLOQUEADO])
def test_slot_ocupado_ou_bloqueado_e_recusado(medica: Medico, joana: Paciente, status: str) -> None:
    slot = _slot(medica, status=status)

    with pytest.raises(SlotIndisponivelError):
        AgendamentoService.agendar(paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.CHAT)

    assert Consulta.objects.count() == 0
    slot.refresh_from_db()
    assert slot.status == status


def test_slot_inexistente_vira_excecao_de_dominio(joana: Paciente) -> None:
    """``DoesNotExist`` é vocabulário do ORM e não pode vazar para o chamador."""
    with pytest.raises(SlotIndisponivelError) as erro:
        AgendamentoService.agendar(paciente=joana, slot_id=987654, origem=Consulta.Origem.CHAT)

    assert not isinstance(erro.value, AgendaSlot.DoesNotExist)
    assert Consulta.objects.count() == 0


def test_slot_no_passado_e_recusado(medica: Medico, joana: Paciente) -> None:
    slot = _slot(medica, data=ONTEM)

    with pytest.raises(SlotNoPassadoError):
        AgendamentoService.agendar(paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.CHAT)

    assert Consulta.objects.count() == 0
    slot.refresh_from_db()
    assert slot.status == AgendaSlot.Status.LIVRE


def test_slot_no_passado_tambem_e_slot_indisponivel(medica: Medico, joana: Paciente) -> None:
    """Hierarquia: quem só quer saber que o horário não serve escreve um ``except``."""
    slot = _slot(medica, data=ONTEM)

    with pytest.raises(SlotIndisponivelError):
        AgendamentoService.agendar(paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.CHAT)

    assert issubclass(SlotNoPassadoError, SlotIndisponivelError)
    assert issubclass(SlotIndisponivelError, AgendamentoError)


def test_mensagens_de_erro_sao_seguras_para_mostrar_ao_paciente(
    medica: Medico, joana: Paciente
) -> None:
    """O chatbot verbaliza ``str(exc)`` direto [S5-12]: nada de detalhe interno."""
    slot = _slot(medica, status=AgendaSlot.Status.BLOQUEADO)

    with pytest.raises(SlotIndisponivelError) as erro:
        AgendamentoService.agendar(paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.CHAT)

    mensagem = str(erro.value)
    assert mensagem
    assert "Traceback" not in mensagem
    # Nem o id do slot, nem o nome de constraint/tabela, nem código do Oracle.
    for vazamento in (str(slot.pk), "UK_SLOT", "ORA-", "CONSULTA", "IntegrityError"):
        assert vazamento not in mensagem


# ---------------------------------------------------------------------------
# Corrida perdida [S3-8]
# ---------------------------------------------------------------------------


def test_corrida_perdida_vira_slot_indisponivel(medica: Medico, joana: Paciente) -> None:
    """``IntegrityError`` do UNIQUE do OneToOne vira a mesma exceção do slot ocupado.

    O cenário é o da transação que passou pela checagem de status (o slot ainda
    constava ``LIVRE``) e só descobriu a colisão no ``INSERT``.
    """
    slot = _slot(medica)
    # Ocupa o slot pelas costas do service, sem mexer no status — é o estado
    # intermediário que a transação perdedora enxerga.
    Consulta.objects.create(paciente=joana, slot=slot, medico=medica)

    atrasado = _paciente(nome="Carlos Lima", cpf="98765432100")
    with pytest.raises(SlotIndisponivelError):
        AgendamentoService.agendar(paciente=atrasado, slot_id=slot.pk, origem=Consulta.Origem.CHAT)

    assert Consulta.objects.count() == 1
    assert Consulta.objects.get().paciente == joana


def test_segunda_consulta_no_mesmo_slot_morre_no_banco(medica: Medico, joana: Paciente) -> None:
    """[S3-8] A prova de que a garantia é do schema, não deste service.

    Sem passar pelo ``AgendamentoService``: o ``UNIQUE`` do ``OneToOneField``
    recusa o segundo ``INSERT`` sozinho. Um bug de concorrência no service — ou
    um script rodando fora dele — não consegue produzir overbooking.
    """
    slot = _slot(medica)
    AgendamentoService.agendar(paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.RECEPCAO)
    atrasado = _paciente(nome="Carlos Lima", cpf="98765432100")

    with pytest.raises(IntegrityError), transaction.atomic():
        Consulta.objects.create(paciente=atrasado, slot=slot, medico=medica)


# ---------------------------------------------------------------------------
# Rollback [S3-7]
# ---------------------------------------------------------------------------


def test_falha_depois_do_insert_nao_deixa_consulta_orfa(
    medica: Medico, joana: Paciente, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A consulta já inserida tem que sumir se a reserva do slot falhar.

    É o ponto exato em que existiria lixo sem o ``atomic()``: consulta gravada e
    slot ainda ``LIVRE``, ou seja, um horário que o chatbot voltaria a oferecer
    para outra pessoa.
    """
    slot = _slot(medica)

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("falha simulada ao reservar o slot")

    monkeypatch.setattr(AgendaSlot, "save", explode)

    with pytest.raises(RuntimeError):
        AgendamentoService.agendar(paciente=joana, slot_id=slot.pk, origem=Consulta.Origem.CHAT)

    monkeypatch.undo()
    assert Consulta.objects.count() == 0
    slot.refresh_from_db()
    assert slot.status == AgendaSlot.Status.LIVRE

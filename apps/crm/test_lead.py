"""Testes do model ``Lead`` — o funil do CRM (S1-8, especificado em S5-22).

Dois pontos concentram o valor destes testes:

* **As etapas são um percurso, não uma máquina de estados travada.** O funil
  precisa aceitar pulo de etapa (a recepção qualifica e agenda no mesmo
  atendimento) e retrocesso (o paciente desmarcou). Se alguém decidir codificar
  a sequência no ``save()`` ou numa ``CheckConstraint``, estes testes quebram —
  que é exatamente a intenção.
* **O ``SET_NULL`` da consulta.** Apagar a consulta não pode levar o lead
  junto: perder a linha apagaria a origem da métrica de conversão do chatbot.

Rodam em SQLite: FK, ``SET_NULL`` e defaults são portáveis.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from django.db.models import ProtectedError

from apps.agenda.models import AgendaSlot, Consulta
from apps.crm.models import Especialidade, Lead, Medico, Paciente

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def retina() -> Especialidade:
    return Especialidade.objects.create(nome="Retina", slug="retina")


def _lead(nome: str = "Marina Souza", **overrides: object) -> Lead:
    dados: dict[str, object] = {"nome": nome}
    dados.update(overrides)
    return Lead.objects.create(**dados)


def _consulta() -> Consulta:
    medico = Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")
    slot = AgendaSlot.objects.create(
        medico=medico,
        data=dt.date(2026, 8, 12),
        hora_inicio=dt.time(9, 0),
        hora_fim=dt.time(9, 30),
    )
    paciente = Paciente(nome="Marina Souza", data_nascimento=dt.date(1990, 2, 2))
    paciente.definir_cpf("12345678909")
    paciente.save()
    return Consulta.objects.create(paciente=paciente, slot=slot, medico=medico)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_lead_nasce_novo_e_sem_vinculo() -> None:
    lead = _lead()

    assert lead.etapa == Lead.Etapa.NOVO
    assert lead.email == ""
    assert lead.telefone == ""
    assert lead.especialidade_interesse is None
    assert lead.conversa_id is None
    assert lead.consulta is None
    assert lead.criado_em is not None
    assert lead.atualizado_em is not None


def test_str_mostra_nome_e_etapa() -> None:
    assert str(_lead()) == "Marina Souza (Novo)"


def test_etapas_seguem_a_ordem_especificada() -> None:
    """A ordem do funil é contrato de [S5-22] e do dashboard de [S5-25]."""
    assert [e.value for e in Lead.Etapa] == [
        "NOVO",
        "QUALIFICADO",
        "AGENDADO",
        "COMPARECEU",
        "RETORNO",
    ]


# ---------------------------------------------------------------------------
# Transição de etapas
# ---------------------------------------------------------------------------


def test_lead_percorre_o_funil_inteiro() -> None:
    lead = _lead()
    for etapa in Lead.Etapa:
        lead.etapa = etapa
        lead.save(update_fields=["etapa"])
        lead.refresh_from_db()
        assert lead.etapa == etapa


def test_lead_pode_pular_etapa() -> None:
    """Recepção qualifica e agenda no mesmo atendimento — sem passar por QUALIFICADO."""
    lead = _lead()
    lead.etapa = Lead.Etapa.AGENDADO
    lead.save(update_fields=["etapa"])

    lead.refresh_from_db()
    assert lead.etapa == Lead.Etapa.AGENDADO


def test_lead_pode_voltar_etapa() -> None:
    """Desmarcou: volta para QUALIFICADO. Nada no schema impede o retrocesso."""
    lead = _lead(etapa=Lead.Etapa.AGENDADO)
    lead.etapa = Lead.Etapa.QUALIFICADO
    lead.save(update_fields=["etapa"])

    lead.refresh_from_db()
    assert lead.etapa == Lead.Etapa.QUALIFICADO


def test_funil_agrupa_por_etapa() -> None:
    """A leitura que o dashboard de [S5-25] faz — e o motivo de IDX_LEAD_ETAPA."""
    _lead("A")
    _lead("B", etapa=Lead.Etapa.QUALIFICADO)
    _lead("C", etapa=Lead.Etapa.QUALIFICADO)

    assert Lead.objects.filter(etapa=Lead.Etapa.NOVO).count() == 1
    assert Lead.objects.filter(etapa=Lead.Etapa.QUALIFICADO).count() == 2


# ---------------------------------------------------------------------------
# Vínculo com a conversa do chatbot
# ---------------------------------------------------------------------------


def test_conversa_id_guarda_a_conversa_inteira_e_nao_um_turno() -> None:
    """Casa com ``InteracaoChat.conversa_id`` sem FK: lá há uma linha por turno."""
    conversa = uuid.uuid4()
    lead = _lead(conversa_id=conversa)

    lead.refresh_from_db()
    assert lead.conversa_id == conversa
    assert Lead.objects.filter(conversa_id=conversa).count() == 1


def test_lead_da_recepcao_nao_tem_conversa() -> None:
    assert _lead(conversa_id=None).conversa_id is None


def test_mesma_pessoa_pode_voltar_em_outra_conversa() -> None:
    """Sem UniqueConstraint: contato repetido meses depois é lead novo, não duplicado."""
    _lead(conversa_id=uuid.uuid4())
    _lead(conversa_id=uuid.uuid4())

    assert Lead.objects.filter(nome="Marina Souza").count() == 2


# ---------------------------------------------------------------------------
# Conversão em consulta [S5-24]
# ---------------------------------------------------------------------------


def test_lead_convertido_aponta_para_a_consulta() -> None:
    consulta = _consulta()
    lead = _lead(consulta=consulta, etapa=Lead.Etapa.AGENDADO)

    lead.refresh_from_db()
    assert lead.consulta == consulta
    assert list(consulta.leads.all()) == [lead]


def test_apagar_consulta_nao_apaga_o_lead() -> None:
    """SET_NULL: o registro de que o contato existiu é a origem da métrica de conversão."""
    consulta = _consulta()
    lead = _lead(consulta=consulta, etapa=Lead.Etapa.AGENDADO)

    consulta.delete()

    lead.refresh_from_db()
    assert lead.consulta is None
    # A etapa **não** é revertida pelo banco: o histórico de que chegou a
    # agendar continua legível no funil.
    assert lead.etapa == Lead.Etapa.AGENDADO
    assert Lead.objects.count() == 1


# ---------------------------------------------------------------------------
# Especialidade de interesse
# ---------------------------------------------------------------------------


def test_lead_registra_a_especialidade_de_interesse(retina: Especialidade) -> None:
    lead = _lead(especialidade_interesse=retina, etapa=Lead.Etapa.QUALIFICADO)

    lead.refresh_from_db()
    assert lead.especialidade_interesse == retina
    assert list(retina.leads.all()) == [lead]


def test_apagar_especialidade_com_lead_e_bloqueado(retina: Especialidade) -> None:
    """PROTECT: apagar a especialidade não pode levar o funil junto."""
    _lead(especialidade_interesse=retina)
    with pytest.raises(ProtectedError):
        retina.delete()


# ---------------------------------------------------------------------------
# Convenções de schema (Oracle)
# ---------------------------------------------------------------------------


def test_tabela_em_upper_snake_case() -> None:
    assert Lead._meta.db_table == "LEAD"


def test_indices_tem_nome_explicito_e_curto() -> None:
    nomes = [c.name for c in Lead._meta.constraints] + [i.name for i in Lead._meta.indexes]

    assert "IDX_LEAD_ETAPA" in nomes
    assert "IDX_LEAD_CONVERSA" in nomes
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"


def test_campos_indexados_nao_pedem_indice_duplicado() -> None:
    """`db_index=True` + índice nomeado na mesma coluna = ORA-01408 no Oracle."""
    for nome_campo in ("etapa", "conversa_id", "especialidade_interesse", "consulta"):
        assert Lead._meta.get_field(nome_campo).db_index is False, nome_campo


def test_nenhum_campo_textfield() -> None:
    """TextField vira NCLOB no Oracle — não é ordenável nem indexável."""
    from django.db import models as dj_models

    for campo in Lead._meta.get_fields():
        assert not isinstance(campo, dj_models.TextField), f"{campo.name} é TextField"

"""Testes do model ``AgendaSlot`` (Bloco 1A do ``docs/CHAT_MVP.md``).

O teste central é o da constraint anti-overbooking ``UK_SLOT_MEDICO_HORARIO``
`[S1-11]`: é a garantia que a ``ARQUITETURA.md`` coloca no banco justamente
para sobreviver a um bug da aplicação. Ele roda em SQLite porque a constraint
é portável — o mesmo cenário no Oracle real fica sob ``@pytest.mark.oracle``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.agenda.models import AgendaSlot
from apps.crm.models import Medico

pytestmark = pytest.mark.django_db

DIA = dt.date(2026, 8, 12)
NOVE_HORAS = dt.time(9, 0)
NOVE_E_MEIA = dt.time(9, 30)


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


def _slot(medico: Medico, **overrides: object) -> AgendaSlot:
    dados: dict[str, object] = {
        "medico": medico,
        "data": DIA,
        "hora_inicio": NOVE_HORAS,
        "hora_fim": NOVE_E_MEIA,
    }
    dados.update(overrides)
    return AgendaSlot.objects.create(**dados)


# ---------------------------------------------------------------------------
# Básico
# ---------------------------------------------------------------------------


def test_slot_nasce_livre(medica: Medico) -> None:
    slot = _slot(medica)
    assert slot.status == AgendaSlot.Status.LIVRE
    assert slot.esta_livre is True
    assert slot.criado_em is not None


def test_slot_bloqueado_nao_esta_livre(medica: Medico) -> None:
    slot = _slot(medica, status=AgendaSlot.Status.BLOQUEADO)
    assert slot.esta_livre is False


def test_slot_str_mostra_medico_data_e_faixa(medica: Medico) -> None:
    slot = _slot(medica)
    assert str(slot) == "Ana Ribeiro — 12/08/2026 09:00–09:30 (LIVRE)"


def test_slots_ordenam_por_data_e_hora(medica: Medico) -> None:
    _slot(medica, hora_inicio=dt.time(11, 0), hora_fim=dt.time(11, 30))
    _slot(medica)
    _slot(medica, data=dt.date(2026, 8, 11), hora_inicio=dt.time(15, 0), hora_fim=dt.time(15, 30))

    ordem = [(s.data, s.hora_inicio) for s in AgendaSlot.objects.all()]
    assert ordem == sorted(ordem)


# ---------------------------------------------------------------------------
# Anti-overbooking [S1-11]
# ---------------------------------------------------------------------------


def test_mesmo_medico_nao_repete_data_e_hora_inicio(medica: Medico) -> None:
    """UK_SLOT_MEDICO_HORARIO: o segundo INSERT tem que morrer no banco."""
    _slot(medica)
    with pytest.raises(IntegrityError), transaction.atomic():
        # Hora de término diferente não salva: a chave é (médico, data, início).
        _slot(medica, hora_fim=dt.time(10, 0))


def test_medicos_diferentes_podem_dividir_o_mesmo_horario(medica: Medico) -> None:
    outro = Medico.objects.create(nome="Bruno Costa", crm_numero="54321", crm_uf="SP")
    _slot(medica)
    _slot(outro)
    assert AgendaSlot.objects.count() == 2


def test_mesmo_medico_pode_ter_horarios_diferentes_no_mesmo_dia(medica: Medico) -> None:
    _slot(medica)
    _slot(medica, hora_inicio=dt.time(10, 0), hora_fim=dt.time(10, 30))
    assert AgendaSlot.objects.count() == 2


def test_apagar_medico_com_agenda_e_bloqueado(medica: Medico) -> None:
    """PROTECT: agenda é histórico clínico, não pode sumir por cascata."""
    _slot(medica)
    with pytest.raises(ProtectedError):
        medica.delete()


# ---------------------------------------------------------------------------
# Convenções de schema (Oracle)
# ---------------------------------------------------------------------------


def test_tabela_em_upper_snake_case() -> None:
    assert AgendaSlot._meta.db_table == "AGENDA_SLOT"


def test_indices_e_constraints_tem_nome_explicito_e_curto() -> None:
    nomes = [c.name for c in AgendaSlot._meta.constraints]
    nomes += [i.name for i in AgendaSlot._meta.indexes]

    assert "UK_SLOT_MEDICO_HORARIO" in nomes
    assert "IDX_SLOT_DATA_STATUS" in nomes
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"

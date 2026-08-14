"""Testes dos models da agenda — ``AgendaSlot`` e ``AgendaRegra``.

O teste central do slot é o da constraint anti-overbooking
``UK_SLOT_MEDICO_HORARIO`` `[S1-11]`: é a garantia que a ``ARQUITETURA.md``
coloca no banco justamente para sobreviver a um bug da aplicação.

Do lado da ``AgendaRegra`` `[S1-8]`, o foco são as invariantes que também moram
no schema (``CK_AGENDA_REGRA_*``) e a chave ``UK_AGENDA_REGRA_JANELA``, que
precisa aceitar dois cenários legítimos — manhã e tarde no mesmo dia, e o
versionamento de regra por vigência que `[S3-5]` vai usar.

Tudo roda em SQLite porque ``CHECK`` e ``UNIQUE`` são portáveis; o mesmo
cenário no Oracle real fica sob ``@pytest.mark.oracle``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.agenda.models import AgendaRegra, AgendaSlot
from apps.crm.models import Medico

pytestmark = pytest.mark.django_db

DIA = dt.date(2026, 8, 12)
NOVE_HORAS = dt.time(9, 0)
NOVE_E_MEIA = dt.time(9, 30)
MEIO_DIA = dt.time(12, 0)
VIGENCIA = dt.date(2026, 9, 1)


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


def _regra(medico: Medico, **overrides: object) -> AgendaRegra:
    dados: dict[str, object] = {
        "medico": medico,
        "dia_semana": AgendaRegra.DiaSemana.TERCA,
        "hora_inicio": NOVE_HORAS,
        "hora_fim": MEIO_DIA,
        "duracao_consulta_min": 30,
        "vigencia_inicio": VIGENCIA,
    }
    dados.update(overrides)
    return AgendaRegra.objects.create(**dados)


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
    nomes += [c.name for c in AgendaRegra._meta.constraints]
    nomes += [i.name for i in AgendaRegra._meta.indexes]

    assert "UK_SLOT_MEDICO_HORARIO" in nomes
    assert "IDX_SLOT_DATA_STATUS" in nomes
    assert "IDX_SLOT_REGRA" in nomes
    assert "UK_AGENDA_REGRA_JANELA" in nomes
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"


# ---------------------------------------------------------------------------
# AgendaRegra — básico [S1-8]
# ---------------------------------------------------------------------------


def test_regra_valida_nasce_ativa_e_sem_prazo(medica: Medico) -> None:
    regra = _regra(medica)

    assert regra.ativo is True
    assert regra.intervalo_min == 0
    assert regra.vigencia_fim is None
    assert regra.criado_em is not None
    assert regra.medico.regras.count() == 1


def test_regra_str_mostra_medico_dia_e_faixa(medica: Medico) -> None:
    assert str(_regra(medica)) == "Ana Ribeiro — Terça-feira 09:00–12:00"


def test_dia_semana_segue_a_convencao_de_date_weekday() -> None:
    """0 = segunda … 6 = domingo, igual a ``date.weekday()`` (não ao ``__week_day``)."""
    assert AgendaRegra.DiaSemana.SEGUNDA == 0
    assert AgendaRegra.DiaSemana.DOMINGO == 6
    # 1º de janeiro de 2026 caiu numa quinta-feira.
    assert dt.date(2026, 1, 1).weekday() == AgendaRegra.DiaSemana.QUINTA


def test_tabela_da_regra_em_upper_snake_case() -> None:
    assert AgendaRegra._meta.db_table == "AGENDA_REGRA"


# ---------------------------------------------------------------------------
# AgendaRegra — CheckConstraints
# ---------------------------------------------------------------------------


def test_horario_invertido_e_recusado_pelo_banco(medica: Medico) -> None:
    """CK_AGENDA_REGRA_HORARIO: hora_fim tem que ser maior que hora_inicio."""
    with pytest.raises(IntegrityError), transaction.atomic():
        _regra(medica, hora_inicio=MEIO_DIA, hora_fim=NOVE_HORAS)


def test_horario_de_largura_zero_e_recusado(medica: Medico) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        _regra(medica, hora_inicio=NOVE_HORAS, hora_fim=NOVE_HORAS)


def test_duracao_zero_e_recusada_pelo_banco(medica: Medico) -> None:
    """CK_AGENDA_REGRA_DURACAO: regra que gera slot de 0 minuto não faz sentido."""
    with pytest.raises(IntegrityError), transaction.atomic():
        _regra(medica, duracao_consulta_min=0)


def test_vigencia_invertida_e_recusada_pelo_banco(medica: Medico) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        _regra(medica, vigencia_fim=VIGENCIA - dt.timedelta(days=1))


def test_vigencia_de_um_unico_dia_e_aceita(medica: Medico) -> None:
    regra = _regra(medica, vigencia_fim=VIGENCIA)
    assert regra.vigencia_fim == regra.vigencia_inicio


# ---------------------------------------------------------------------------
# AgendaRegra — UK_AGENDA_REGRA_JANELA
# ---------------------------------------------------------------------------


def test_regra_identica_e_recusada(medica: Medico) -> None:
    """A chave é (médico, dia da semana, hora de início, início da vigência)."""
    _regra(medica)
    with pytest.raises(IntegrityError), transaction.atomic():
        # Mesmo com fim de expediente diferente: o resto da chave repete.
        _regra(medica, hora_fim=dt.time(11, 0))


def test_mesmo_medico_pode_ter_manha_e_tarde_no_mesmo_dia(medica: Medico) -> None:
    """Motivo de a chave não ser (médico, dia_semana)."""
    _regra(medica)
    _regra(medica, hora_inicio=dt.time(14, 0), hora_fim=dt.time(18, 0))
    assert AgendaRegra.objects.count() == 2


def test_mesma_janela_em_vigencia_nova_e_aceita(medica: Medico) -> None:
    """Versionamento de regra que mudou no meio — o cenário de [S3-5]."""
    antiga = _regra(medica, vigencia_fim=VIGENCIA + dt.timedelta(days=29))
    nova = _regra(
        medica,
        vigencia_inicio=antiga.vigencia_fim + dt.timedelta(days=1),
        duracao_consulta_min=20,
    )

    assert AgendaRegra.objects.count() == 2
    assert nova.vigencia_inicio > antiga.vigencia_inicio


def test_medicos_diferentes_podem_ter_a_mesma_janela(medica: Medico) -> None:
    outro = Medico.objects.create(nome="Bruno Costa", crm_numero="54321", crm_uf="SP")
    _regra(medica)
    _regra(outro)
    assert AgendaRegra.objects.count() == 2


# ---------------------------------------------------------------------------
# Vínculo AgendaRegra ↔ AgendaSlot
# ---------------------------------------------------------------------------


def test_slot_sem_regra_continua_valido(medica: Medico) -> None:
    """Slots semeados à mão não têm procedência — por isso a FK é nullable."""
    slot = _slot(medica)
    assert slot.regra is None


def test_slot_pode_apontar_para_a_regra_que_o_gerou(medica: Medico) -> None:
    regra = _regra(medica)
    slot = _slot(medica, regra=regra)

    slot.refresh_from_db()
    assert slot.regra == regra
    assert list(regra.slots.all()) == [slot]


def test_apagar_regra_com_slots_e_bloqueado(medica: Medico) -> None:
    """PROTECT: apagar a regra deixaria slots órfãos e cegaria o [S3-5]."""
    regra = _regra(medica)
    _slot(medica, regra=regra)

    with pytest.raises(ProtectedError):
        regra.delete()


def test_apagar_medico_com_regra_e_bloqueado(medica: Medico) -> None:
    _regra(medica)
    with pytest.raises(ProtectedError):
        medica.delete()

"""Testes dos models da agenda — ``AgendaSlot``, ``AgendaRegra`` e ``Consulta``.

O teste central do slot é o da constraint anti-overbooking
``UK_SLOT_MEDICO_HORARIO`` `[S1-11]`: é a garantia que a ``ARQUITETURA.md``
coloca no banco justamente para sobreviver a um bug da aplicação. O da
``Consulta`` `[S1-8]` é o par dessa garantia na outra ponta: o ``OneToOne``
para o slot, que impede duas consultas no mesmo horário mesmo que o service de
agendamento `[S3-7]` (que ainda não existe) tenha um bug de concorrência.

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

from apps.agenda.models import AgendaRegra, AgendaSlot, Consulta
from apps.crm.models import Medico, Paciente

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


# ---------------------------------------------------------------------------
# Consulta — básico [S1-8]
# ---------------------------------------------------------------------------


def _paciente(nome: str = "Joana Prado", cpf: str = "12345678909") -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=dt.date(1980, 5, 17))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


@pytest.fixture
def joana() -> Paciente:
    return _paciente()


def _consulta(paciente: Paciente, slot: AgendaSlot, **overrides: object) -> Consulta:
    dados: dict[str, object] = {
        "paciente": paciente,
        "slot": slot,
        # Cópia deliberada de ``slot.medico`` — no fluxo real quem preenche é o
        # AgendamentoService [S3-7], que ainda não existe.
        "medico": slot.medico,
    }
    dados.update(overrides)
    return Consulta.objects.create(**dados)


def test_consulta_nasce_agendada_e_pela_recepcao(medica: Medico, joana: Paciente) -> None:
    consulta = _consulta(joana, _slot(medica))

    assert consulta.status == Consulta.Status.AGENDADA
    assert consulta.origem == Consulta.Origem.RECEPCAO
    assert consulta.observacoes == ""
    assert consulta.criado_em is not None
    assert consulta.atualizado_em is not None


def test_consulta_do_chat_registra_a_origem(medica: Medico, joana: Paciente) -> None:
    """``origem`` é o denominador da métrica de conversão do chatbot [S5-28]."""
    consulta = _consulta(joana, _slot(medica), origem=Consulta.Origem.CHAT)
    assert consulta.origem == Consulta.Origem.CHAT


def test_consulta_str_mostra_paciente_data_e_status(medica: Medico, joana: Paciente) -> None:
    consulta = _consulta(joana, _slot(medica))
    assert str(consulta) == "Joana Prado — 12/08/2026 09:00 (AGENDADA)"


def test_consulta_e_alcancavel_pelos_dois_lados(medica: Medico, joana: Paciente) -> None:
    slot = _slot(medica)
    consulta = _consulta(joana, slot)

    slot.refresh_from_db()
    assert slot.consulta == consulta
    assert list(joana.consultas.all()) == [consulta]
    assert list(medica.consultas.all()) == [consulta]


def test_medico_da_consulta_e_copia_do_slot(medica: Medico, joana: Paciente) -> None:
    """Desnormalização deliberada: "minha agenda" [S3-12] lê sem join."""
    slot = _slot(medica)
    consulta = _consulta(joana, slot)
    assert consulta.medico_id == slot.medico_id


# ---------------------------------------------------------------------------
# Consulta — anti-overbooking (OneToOne com o slot)
# ---------------------------------------------------------------------------


def test_duas_consultas_no_mesmo_slot_sao_recusadas(medica: Medico, joana: Paciente) -> None:
    """O OneToOne é a barreira que sobrevive a um bug de concorrência em [S3-7]."""
    slot = _slot(medica)
    _consulta(joana, slot)
    outro = _paciente(nome="Carlos Lima", cpf="98765432100")

    with pytest.raises(IntegrityError), transaction.atomic():
        _consulta(outro, slot)


def test_paciente_pode_ter_consultas_em_slots_diferentes(medica: Medico, joana: Paciente) -> None:
    _consulta(joana, _slot(medica))
    _consulta(joana, _slot(medica, hora_inicio=dt.time(10, 0), hora_fim=dt.time(10, 30)))
    assert joana.consultas.count() == 2


def test_slot_de_consulta_cancelada_continua_ocupado(medica: Medico, joana: Paciente) -> None:
    """Cancelar muda o status; liberar o horário é decisão de [S3-7], não do model."""
    slot = _slot(medica)
    consulta = _consulta(joana, slot)
    consulta.status = Consulta.Status.CANCELADA
    consulta.save(update_fields=["status"])

    outro = _paciente(nome="Carlos Lima", cpf="98765432100")
    with pytest.raises(IntegrityError), transaction.atomic():
        _consulta(outro, slot)


# ---------------------------------------------------------------------------
# Consulta — PROTECT nos três lados
# ---------------------------------------------------------------------------


def test_apagar_paciente_com_consulta_e_bloqueado(medica: Medico, joana: Paciente) -> None:
    """Retenção CFM: consulta é histórico clínico, arquivar usa ``Paciente.ativo``."""
    _consulta(joana, _slot(medica))
    with pytest.raises(ProtectedError):
        joana.delete()


def test_apagar_medico_com_consulta_e_bloqueado(medica: Medico, joana: Paciente) -> None:
    _consulta(joana, _slot(medica))
    with pytest.raises(ProtectedError):
        medica.delete()


def test_apagar_slot_com_consulta_e_bloqueado(medica: Medico, joana: Paciente) -> None:
    """Apagar o slot apagaria a prova de quando a consulta foi marcada."""
    slot = _slot(medica)
    _consulta(joana, slot)
    with pytest.raises(ProtectedError):
        slot.delete()


# ---------------------------------------------------------------------------
# Consulta — convenções de schema (Oracle)
# ---------------------------------------------------------------------------


def test_tabela_da_consulta_em_upper_snake_case() -> None:
    assert Consulta._meta.db_table == "CONSULTA"


def test_indices_da_consulta_tem_nome_explicito_e_curto() -> None:
    nomes = [c.name for c in Consulta._meta.constraints]
    nomes += [i.name for i in Consulta._meta.indexes]

    assert "IDX_CONSULTA_PACIENTE" in nomes
    assert "IDX_CONSULTA_STATUS" in nomes
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"


def test_fks_da_consulta_nao_criam_indice_duplicado() -> None:
    """`db_index=True` + índice nomeado (ou UNIQUE) na mesma coluna = ORA-01408."""
    for nome_campo in ("paciente", "slot", "medico"):
        assert Consulta._meta.get_field(nome_campo).db_index is False, nome_campo


def test_consulta_nao_tem_campo_textfield() -> None:
    """TextField vira NCLOB no Oracle — ``observacoes`` entra em WHERE/ORDER BY."""
    from django.db import models as dj_models

    for campo in Consulta._meta.get_fields():
        assert not isinstance(campo, dj_models.TextField), f"{campo.name} é TextField"

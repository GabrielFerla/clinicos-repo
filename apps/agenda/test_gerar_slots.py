"""Testes do comando ``gerar_slots`` — a expansão de regra em agenda (S3-3).

Três coisas são verificadas aqui com mais rigor que o resto, porque são as que
quebram feio e em silêncio:

1. **A convenção de ``dia_semana``.** ``AgendaRegra`` usa 0 = segunda … 6 =
   domingo (igual a ``date.weekday()``), e não a do lookup ``__week_day`` do
   Django (1 = domingo). Um erro de um dia aqui gera agenda inteira no dia
   errado sem levantar exceção nenhuma, então
   ``test_regra_gera_apenas_no_dia_da_semana_declarado`` percorre os sete dias.
2. **A borda da janela.** Slot que estoura ``hora_fim`` invade o que vem depois
   (almoço, outro médico, o fim do expediente) e só aparece na tela da recepção.
3. **A idempotência.** A `[S3-4]` vai chamar este comando todo dia pelo Celery
   Beat, sobre uma janela que se sobrepõe quase inteira à da véspera. Segunda
   execução que duplique linha esbarra em ``UK_SLOT_MEDICO_HORARIO`` e derruba o
   job.

As datas são todas calculadas a partir de ``timezone.localdate()`` — a mesma
função que o comando usa — em vez de fixadas em constantes: a janela é relativa
a "hoje" por definição, e um teste com data fixa passaria a mentir amanhã.

Roda em SQLite, como o resto da suíte.
"""

from __future__ import annotations

import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.agenda.models import AgendaRegra, AgendaSlot
from apps.crm.models import Medico

pytestmark = pytest.mark.django_db

OITO = dt.time(8, 0)
DEZ = dt.time(10, 0)
MEIO_DIA = dt.time(12, 0)


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


@pytest.fixture
def outro_medico() -> Medico:
    return Medico.objects.create(nome="Bruno Costa", crm_numero="54321", crm_uf="SP")


def _hoje() -> dt.date:
    return timezone.localdate()


def _regra(medico: Medico, **overrides: object) -> AgendaRegra:
    """Regra padrão do arquivo: segunda-feira, 08:00–12:00, 30 min, sem intervalo."""
    dados: dict[str, object] = {
        "medico": medico,
        "dia_semana": AgendaRegra.DiaSemana.SEGUNDA,
        "hora_inicio": OITO,
        "hora_fim": MEIO_DIA,
        "duracao_consulta_min": 30,
        "intervalo_min": 0,
        # No passado, para que a vigência não interfira nos testes que não são
        # sobre vigência.
        "vigencia_inicio": _hoje() - dt.timedelta(days=30),
    }
    dados.update(overrides)
    return AgendaRegra.objects.create(**dados)


def _gerar(**opcoes: object) -> str:
    """Roda o comando e devolve o que ele escreveu no stdout."""
    saida = StringIO()
    call_command("gerar_slots", stdout=saida, stderr=StringIO(), **opcoes)
    return saida.getvalue()


def _datas_da_janela(dias: int) -> list[dt.date]:
    """As datas que o comando deve percorrer, incluindo as duas pontas."""
    hoje = _hoje()
    return [hoje + dt.timedelta(days=n) for n in range(dias + 1)]


def _datas_no_dia_da_semana(dias: int, dia_semana: int) -> list[dt.date]:
    return [data for data in _datas_da_janela(dias) if data.weekday() == dia_semana]


def _horarios_em(data: dt.date) -> list[tuple[dt.time, dt.time]]:
    return list(
        AgendaSlot.objects.filter(data=data)
        .order_by("hora_inicio")
        .values_list("hora_inicio", "hora_fim")
    )


# ---------------------------------------------------------------------------
# Expansão da regra
# ---------------------------------------------------------------------------


def test_janela_de_quatro_horas_com_consultas_de_meia_hora_gera_oito_slots(
    medica: Medico,
) -> None:
    """O caso do DoD: segunda, 08:00–12:00, 30 min, sem intervalo."""
    _regra(medica)

    _gerar(dias=14)

    segundas = _datas_no_dia_da_semana(14, 0)
    assert segundas, "janela de 14 dias sempre contém ao menos uma segunda-feira"
    assert AgendaSlot.objects.count() == 8 * len(segundas)

    esperado = [
        (dt.time(8, 0), dt.time(8, 30)),
        (dt.time(8, 30), dt.time(9, 0)),
        (dt.time(9, 0), dt.time(9, 30)),
        (dt.time(9, 30), dt.time(10, 0)),
        (dt.time(10, 0), dt.time(10, 30)),
        (dt.time(10, 30), dt.time(11, 0)),
        (dt.time(11, 0), dt.time(11, 30)),
        (dt.time(11, 30), dt.time(12, 0)),
    ]
    for segunda in segundas:
        assert _horarios_em(segunda) == esperado


@pytest.mark.parametrize("dia_semana", list(range(7)))
def test_regra_gera_apenas_no_dia_da_semana_declarado(medica: Medico, dia_semana: int) -> None:
    """0 = segunda … 6 = domingo, igual a ``date.weekday()``.

    Este é o teste que pega a conversão indevida para a convenção do lookup
    ``__week_day`` do Django (1 = domingo): sob ela, uma regra declarada como 6
    (domingo) cairia em sexta-feira, e nada no banco reclamaria.
    """
    _regra(medica, dia_semana=dia_semana)

    _gerar(dias=14)

    dias_gerados = set(AgendaSlot.objects.values_list("data", flat=True))
    assert dias_gerados, "toda janela de 14 dias contém os sete dias da semana"
    assert {data.weekday() for data in dias_gerados} == {dia_semana}


def test_intervalo_desloca_o_inicio_da_consulta_seguinte(medica: Medico) -> None:
    """08:00–10:00, consultas de 45 min com 15 de folga: o terceiro slot não cabe."""
    _regra(medica, hora_fim=DEZ, duracao_consulta_min=45, intervalo_min=15)

    _gerar(dias=14)

    segunda = _datas_no_dia_da_semana(14, 0)[0]
    assert _horarios_em(segunda) == [
        (dt.time(8, 0), dt.time(8, 45)),
        (dt.time(9, 0), dt.time(9, 45)),
    ]


def test_nenhum_slot_ultrapassa_a_hora_fim_da_regra(medica: Medico) -> None:
    """Janela de 1h10 com consultas de 30 min: o terceiro slot terminaria às 09:30."""
    _regra(medica, hora_fim=dt.time(9, 10), duracao_consulta_min=30)

    _gerar(dias=14)

    segunda = _datas_no_dia_da_semana(14, 0)[0]
    assert _horarios_em(segunda) == [
        (dt.time(8, 0), dt.time(8, 30)),
        (dt.time(8, 30), dt.time(9, 0)),
    ]
    assert not AgendaSlot.objects.filter(hora_fim__gt=dt.time(9, 10)).exists()


def test_slot_gerado_guarda_a_regra_de_origem(medica: Medico) -> None:
    """Procedência que a [S3-5] precisa para achar os slots de uma regra que mudou."""
    regra = _regra(medica)

    _gerar(dias=14)

    assert AgendaSlot.objects.exists()
    assert not AgendaSlot.objects.exclude(regra=regra).exists()
    assert regra.slots.count() == AgendaSlot.objects.count()


def test_slot_gerado_nasce_livre(medica: Medico) -> None:
    _regra(medica)

    _gerar(dias=14)

    assert not AgendaSlot.objects.exclude(status=AgendaSlot.Status.LIVRE).exists()


# ---------------------------------------------------------------------------
# Janela
# ---------------------------------------------------------------------------


def test_janela_vai_de_hoje_ate_hoje_mais_dias_inclusive(medica: Medico) -> None:
    hoje = _hoje()
    ultimo_dia = hoje + dt.timedelta(days=10)
    _regra(medica, dia_semana=ultimo_dia.weekday())

    _gerar(dias=10)

    datas = set(AgendaSlot.objects.values_list("data", flat=True))
    assert ultimo_dia in datas, "a última ponta da janela entra"
    assert min(datas) >= hoje, "agenda para trás é histórico, não é geração"
    assert max(datas) <= ultimo_dia


def test_nao_gera_nada_depois_do_fim_da_janela(medica: Medico) -> None:
    _regra(medica)

    _gerar(dias=7)

    assert not AgendaSlot.objects.filter(data__gt=_hoje() + dt.timedelta(days=7)).exists()


def test_dias_negativo_e_recusado(medica: Medico) -> None:
    _regra(medica)

    with pytest.raises(CommandError):
        _gerar(dias=-1)

    assert not AgendaSlot.objects.exists()


# ---------------------------------------------------------------------------
# Idempotência — o requisito que sustenta o job diário da [S3-4]
# ---------------------------------------------------------------------------


def test_segunda_execucao_nao_cria_slot_novo(medica: Medico) -> None:
    _regra(medica)
    _gerar(dias=30)
    antes = list(AgendaSlot.objects.order_by("id").values_list("id", "data", "hora_inicio"))

    saida = _gerar(dias=30)  # não pode duplicar nada nem levantar exceção

    assert antes
    assert list(AgendaSlot.objects.order_by("id").values_list("id", "data", "hora_inicio")) == antes
    assert "0 slots criados" in saida
    assert f"{len(antes)} já existiam" in saida


def test_execucao_seguinte_completa_a_janela_sem_refazer_o_que_ja_existe(medica: Medico) -> None:
    """É o que o Celery Beat da [S3-4] faz todo dia: mesma regra, janela deslocada."""
    _regra(medica)
    _gerar(dias=7)
    gerados_na_primeira = AgendaSlot.objects.count()

    _gerar(dias=21)

    assert AgendaSlot.objects.count() > gerados_na_primeira
    assert AgendaSlot.objects.filter(regra__isnull=True).count() == 0


def test_slot_existente_nao_e_alterado(medica: Medico) -> None:
    """Slot RESERVADO/BLOQUEADO é trabalho humano — o comando só cria."""
    regra = _regra(medica)
    segunda = _datas_no_dia_da_semana(14, 0)[0]
    reservado = AgendaSlot.objects.create(
        medico=medica,
        data=segunda,
        hora_inicio=OITO,
        hora_fim=dt.time(8, 30),
        status=AgendaSlot.Status.RESERVADO,
    )

    _gerar(dias=14)

    reservado.refresh_from_db()
    assert reservado.status == AgendaSlot.Status.RESERVADO
    assert reservado.regra_id is None, "o comando não reescreve a procedência de slot alheio"
    # O horário ocupado não vira um segundo slot: continua um só, e o resto da
    # segunda-feira foi preenchido normalmente pela regra.
    assert AgendaSlot.objects.filter(data=segunda, hora_inicio=OITO).count() == 1
    assert AgendaSlot.objects.filter(data=segunda, regra=regra).count() == 7


# ---------------------------------------------------------------------------
# Filtros: ativo, vigência e --medico
# ---------------------------------------------------------------------------


def test_regra_inativa_nao_gera_nada(medica: Medico) -> None:
    _regra(medica, ativo=False)

    saida = _gerar(dias=30)

    assert not AgendaSlot.objects.exists()
    assert "Nenhuma regra de agenda ativa" in saida


def test_regra_com_vigencia_ainda_no_futuro_nao_gera_nada(medica: Medico) -> None:
    _regra(medica, vigencia_inicio=_hoje() + dt.timedelta(days=365))

    _gerar(dias=30)

    assert not AgendaSlot.objects.exists()


def test_regra_com_vigencia_encerrada_nao_gera_nada(medica: Medico) -> None:
    _regra(
        medica,
        vigencia_inicio=_hoje() - dt.timedelta(days=60),
        vigencia_fim=_hoje() - dt.timedelta(days=1),
    )

    _gerar(dias=30)

    assert not AgendaSlot.objects.exists()


def test_vigencia_delimita_as_datas_geradas(medica: Medico) -> None:
    """Regra que só começa a valer no meio da janela não gera nada antes disso."""
    inicio = _hoje() + dt.timedelta(days=10)
    fim = _hoje() + dt.timedelta(days=20)
    _regra(medica, vigencia_inicio=inicio, vigencia_fim=fim)

    _gerar(dias=30)

    datas = set(AgendaSlot.objects.values_list("data", flat=True))
    assert datas, "há ao menos uma segunda-feira entre o 10º e o 20º dia"
    assert min(datas) >= inicio
    assert max(datas) <= fim


def test_medico_restringe_a_geracao(medica: Medico, outro_medico: Medico) -> None:
    _regra(medica)
    _regra(outro_medico)

    _gerar(dias=14, medico=medica.pk)

    assert AgendaSlot.objects.exists()
    assert not AgendaSlot.objects.exclude(medico=medica).exists()


def test_sem_medico_gera_para_todos(medica: Medico, outro_medico: Medico) -> None:
    _regra(medica)
    _regra(outro_medico)

    _gerar(dias=14)

    assert AgendaSlot.objects.filter(medico=medica).exists()
    assert AgendaSlot.objects.filter(medico=outro_medico).exists()


def test_medico_sem_regra_avisa_e_nao_gera(medica: Medico, outro_medico: Medico) -> None:
    _regra(medica)

    saida = _gerar(dias=14, medico=outro_medico.pk)

    assert not AgendaSlot.objects.exists()
    assert "Nenhuma regra de agenda ativa" in saida


# ---------------------------------------------------------------------------
# Saída e --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_nao_grava_nada(medica: Medico) -> None:
    _regra(medica)

    saida = _gerar(dias=14, dry_run=True)

    assert not AgendaSlot.objects.exists()
    assert "[dry-run]" in saida
    assert f"{8 * len(_datas_no_dia_da_semana(14, 0))} slots seriam criados" in saida


def test_saida_reporta_regras_criados_e_existentes(medica: Medico) -> None:
    _regra(medica)
    _regra(medica, dia_semana=AgendaRegra.DiaSemana.TERCA)

    saida = _gerar(dias=14)

    assert "2 regras processadas" in saida
    assert f"{AgendaSlot.objects.count()} slots criados" in saida
    assert "0 já existiam" in saida


def test_janelas_sobrepostas_geram_o_horario_uma_vez_so(medica: Medico) -> None:
    """08:00–12:00 e 09:00–10:00 no mesmo dia convivem no schema (ver AgendaRegra)."""
    _regra(medica)
    _regra(medica, hora_inicio=dt.time(9, 0), hora_fim=DEZ)

    saida = _gerar(dias=14)

    segunda = _datas_no_dia_da_semana(14, 0)[0]
    assert AgendaSlot.objects.filter(data=segunda).count() == 8
    assert "janelas sobrepostas" in saida

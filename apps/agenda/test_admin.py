"""Testes do Admin da agenda `[S3-10]` — regras, slots e consultas.

O Admin é a UI de operação da agenda no MVP1 (ADR-0005), então "a listagem
abre" é requisito de produto, não trivialidade. Dois pontos merecem teste de
verdade:

* **O N+1 da listagem de consultas.** ``Consulta.__str__`` lê ``paciente.nome``
  e ``slot.data``, e as colunas de data e hora saem do slot. Sem
  ``list_select_related`` cada linha custa três queries — o tipo de regressão
  que passa despercebida em base de teste e derruba a tela em produção. O teste
  compara o número de queries com 1 e com 5 consultas.
* **A invariante ``consulta.medico == slot.medico``.** O médico não está no
  formulário; quem o preenche é ``ConsultaAdmin.save_model``, a partir do slot.

Rodam em SQLite, como o resto da suíte.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.agenda.models import AgendaRegra, AgendaSlot, Consulta
from apps.crm.models import Medico, Paciente

pytestmark = pytest.mark.django_db

DIA = dt.date(2026, 9, 15)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client_logado() -> Client:
    usuario = get_user_model().objects.create_superuser(
        username="recepcao_agenda",
        email="agenda@example.com",
        password="senha-de-teste",  # noqa: S106
    )
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


def _paciente(nome: str, cpf: str) -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=dt.date(1985, 1, 20))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


def _slot(medico: Medico, hora: dt.time) -> AgendaSlot:
    fim = (dt.datetime.combine(DIA, hora) + dt.timedelta(minutes=30)).time()
    return AgendaSlot.objects.create(medico=medico, data=DIA, hora_inicio=hora, hora_fim=fim)


def _consulta(medico: Medico, hora: dt.time, paciente: Paciente, **overrides: object) -> Consulta:
    return Consulta.objects.create(
        paciente=paciente, slot=_slot(medico, hora), medico=medico, **overrides
    )


@pytest.fixture
def regra(medica: Medico) -> AgendaRegra:
    return AgendaRegra.objects.create(
        medico=medica,
        dia_semana=AgendaRegra.DiaSemana.TERCA,
        hora_inicio=dt.time(8, 0),
        hora_fim=dt.time(12, 0),
        duracao_consulta_min=30,
        vigencia_inicio=dt.date(2026, 9, 1),
    )


# ---------------------------------------------------------------------------
# AgendaRegra
# ---------------------------------------------------------------------------


def test_listagem_de_regras_carrega(admin_client_logado: Client, regra: AgendaRegra) -> None:
    resposta = admin_client_logado.get(reverse("admin:agenda_agendaregra_changelist"))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "Ana Ribeiro" in corpo
    # O rótulo do ``choices``, não o número cru.
    assert "Terça-feira" in corpo


def test_regra_sem_prazo_mostra_vigencia_aberta(
    admin_client_logado: Client, regra: AgendaRegra
) -> None:
    resposta = admin_client_logado.get(reverse("admin:agenda_agendaregra_changelist"))

    assert "desde 01/09/2026" in resposta.content.decode()


def test_regra_com_prazo_mostra_o_intervalo(admin_client_logado: Client, medica: Medico) -> None:
    AgendaRegra.objects.create(
        medico=medica,
        dia_semana=AgendaRegra.DiaSemana.QUARTA,
        hora_inicio=dt.time(14, 0),
        hora_fim=dt.time(18, 0),
        duracao_consulta_min=20,
        vigencia_inicio=dt.date(2026, 9, 1),
        vigencia_fim=dt.date(2026, 12, 31),
    )

    resposta = admin_client_logado.get(reverse("admin:agenda_agendaregra_changelist"))

    assert "01/09/2026 – 31/12/2026" in resposta.content.decode()


def test_filtro_de_regras_por_dia_da_semana(
    admin_client_logado: Client, regra: AgendaRegra
) -> None:
    resposta = admin_client_logado.get(
        reverse("admin:agenda_agendaregra_changelist"),
        {"dia_semana__exact": str(AgendaRegra.DiaSemana.QUINTA.value)},
    )

    assert list(resposta.context["cl"].queryset) == []


def test_formulario_de_regra_abre(admin_client_logado: Client) -> None:
    resposta = admin_client_logado.get(reverse("admin:agenda_agendaregra_add"))
    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------


def test_listagem_de_consultas_carrega(admin_client_logado: Client, medica: Medico) -> None:
    _consulta(medica, dt.time(9, 0), _paciente("Joana Prado", "12345678909"))

    resposta = admin_client_logado.get(reverse("admin:agenda_consulta_changelist"))
    corpo = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Joana Prado" in corpo
    assert "15/09/2026" in corpo
    assert "09:00" in corpo


def test_listagem_de_consultas_nao_escala_em_queries(
    admin_client_logado: Client, medica: Medico
) -> None:
    """Sem ``list_select_related`` cada linha custaria três queries a mais."""
    url = reverse("admin:agenda_consulta_changelist")
    _consulta(medica, dt.time(8, 0), _paciente("Primeira", "12345678909"))
    with CaptureQueriesContext(connection) as com_uma:
        admin_client_logado.get(url)

    for i, hora in enumerate([dt.time(9, 0), dt.time(10, 0), dt.time(11, 0), dt.time(14, 0)]):
        _consulta(medica, hora, _paciente(f"Paciente {i}", f"1114447773{i}"))
    with CaptureQueriesContext(connection) as com_cinco:
        admin_client_logado.get(url)

    assert Consulta.objects.count() == 5
    assert len(com_cinco) == len(com_uma)


def test_filtro_de_consultas_por_status(admin_client_logado: Client, medica: Medico) -> None:
    agendada = _consulta(medica, dt.time(9, 0), _paciente("Agendada", "12345678909"))
    _consulta(
        medica,
        dt.time(10, 0),
        _paciente("Cancelada", "98765432100"),
        status=Consulta.Status.CANCELADA,
    )

    resposta = admin_client_logado.get(
        reverse("admin:agenda_consulta_changelist"),
        {"status__exact": Consulta.Status.AGENDADA},
    )

    assert list(resposta.context["cl"].queryset) == [agendada]


def test_busca_de_consulta_por_nome_do_paciente(
    admin_client_logado: Client, medica: Medico
) -> None:
    joana = _consulta(medica, dt.time(9, 0), _paciente("Joana Prado", "12345678909"))
    _consulta(medica, dt.time(10, 0), _paciente("Outro Qualquer", "98765432100"))

    resposta = admin_client_logado.get(reverse("admin:agenda_consulta_changelist"), {"q": "Joana"})

    assert list(resposta.context["cl"].queryset) == [joana]


def test_cadastro_de_consulta_deriva_o_medico_do_slot(
    admin_client_logado: Client, medica: Medico
) -> None:
    """O médico não está no formulário — quem o preenche é ``save_model``."""
    paciente = _paciente("Joana Prado", "12345678909")
    slot = _slot(medica, dt.time(9, 0))

    resposta = admin_client_logado.post(
        reverse("admin:agenda_consulta_add"),
        {
            "paciente": str(paciente.pk),
            "slot": str(slot.pk),
            "status": Consulta.Status.AGENDADA,
            "origem": Consulta.Origem.RECEPCAO,
            "observacoes": "",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    consulta = Consulta.objects.get(slot=slot)
    assert consulta.medico == medica == consulta.slot.medico


def test_medico_e_somente_leitura_no_formulario_de_consulta() -> None:
    from django.contrib.admin.sites import site

    assert "medico" in site._registry[Consulta].readonly_fields

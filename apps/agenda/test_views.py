"""Testes da tela **Consultas do dia** `[S4-4]`.

A tela é de leitura, então o que merece teste não é "renderiza", e sim as três
coisas que, quebradas, quebram em silêncio:

* **O recorte por perfil.** A página lista nomes de pacientes. ``RECEPCAO`` vê a
  clínica inteira, ``MEDICO`` vê só o que passa por ele, e ``MEDICO`` sem
  ``Medico`` vinculado não vê nada — o default é o fechado. É a mesma regra do
  ``RestritoAoMedicoMixin``, reimplementada fora do Admin, e uma regra
  duplicada só continua verdadeira enquanto houver teste dos dois lados.
* **O N+1 da grade.** Cada linha lê ``paciente.nome``, ``medico.nome`` e
  ``slot.hora_inicio``. Sem o ``select_related`` da view isso custa três
  queries por consulta, numa tela que a recepção deixa aberta o dia inteiro. O
  teste compara o custo com 1 e com 5 consultas.
* **As contagens da barra lateral falam do dia inteiro, não do recorte.** É
  decisão de produto, e a implementação natural (contar sobre a lista já
  filtrada) a viola. Sem teste, o próximo refactor "simplifica" isso de volta.

O ``dia`` da querystring é recortado em faixa: um ``?dia=999`` não pode passar
adiante como offset de data.

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
from django.utils import timezone

from apps.agenda.models import AgendaSlot, Consulta
from apps.agenda.services.agendamento import AgendamentoService
from apps.agenda.views import DIAS_NA_REGUA
from apps.crm.models import Medico, Paciente

pytestmark = pytest.mark.django_db

SENHA = "senha-de-teste"  # noqa: S105


# ---------------------------------------------------------------------------
# Fixtures — o dia é sempre "hoje", porque a view parte de `localdate()`
# ---------------------------------------------------------------------------


@pytest.fixture
def hoje() -> dt.date:
    return timezone.localdate()


def _usuario(username: str, perfil: str) -> object:
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=SENHA,
        perfil=perfil,
        is_staff=True,
    )


def _cliente(usuario: object) -> Client:
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


def _paciente(nome: str, cpf: str) -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=dt.date(1985, 1, 20))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


def _slot(medico: Medico, dia: dt.date, hora: dt.time) -> AgendaSlot:
    fim = (dt.datetime.combine(dia, hora) + dt.timedelta(minutes=30)).time()
    return AgendaSlot.objects.create(medico=medico, data=dia, hora_inicio=hora, hora_fim=fim)


def _consulta(
    medico: Medico,
    paciente: Paciente,
    dia: dt.date,
    hora: dt.time,
    **extras: object,
) -> Consulta:
    """Cria pelo serviço, que é quem também marca o slot como ocupado.

    O serviço recebe ``slot_id`` e não a instância: a linha é relida sob lock
    dentro da transação, e um objeto carregado antes da chamada já está
    desatualizado por definição.
    """
    consulta = AgendamentoService.agendar(
        slot_id=_slot(medico, dia, hora).pk,
        paciente=paciente,
        origem=extras.pop("origem", Consulta.Origem.RECEPCAO),
    )
    if extras:
        for campo, valor in extras.items():
            setattr(consulta, campo, valor)
        consulta.save()
    return consulta


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="RS")


@pytest.fixture
def medico_outro() -> Medico:
    return Medico.objects.create(nome="Bruno Carvalho", crm_numero="23456", crm_uf="RS")


# ---------------------------------------------------------------------------
# Acesso
# ---------------------------------------------------------------------------


def test_anonimo_e_mandado_para_um_login_que_existe() -> None:
    """Não basta redirecionar: tem de redirecionar para uma rota real.

    O default do Django é ``/accounts/login/``, que este projeto não serve — a
    única tela de login é a do Admin. Sem o ``LOGIN_URL`` em
    ``config/settings/base.py`` este redirecionamento cai num 404, e o sintoma
    só aparece para quem está deslogado.
    """
    resposta = Client().get(reverse("agenda:consultas"))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("admin:login"))
    assert "next=/agenda/" in resposta.url

    # E a rota de destino responde de verdade.
    assert Client().get(reverse("admin:login")).status_code == 200


def test_recepcao_ve_a_clinica_inteira(hoje: dt.date, medica: Medico, medico_outro: Medico) -> None:
    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))
    _consulta(medico_outro, _paciente("Otávio Dias", "52998224725"), hoje, dt.time(9, 0))

    resposta = _cliente(_usuario("recepcao", "RECEPCAO")).get(reverse("agenda:consultas"))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "Helena Costa" in corpo
    assert "Otávio Dias" in corpo


def test_medico_ve_so_as_proprias_consultas(
    hoje: dt.date, medica: Medico, medico_outro: Medico
) -> None:
    usuario = _usuario("ana", "MEDICO")
    medica.usuario = usuario
    medica.save()

    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))
    _consulta(medico_outro, _paciente("Otávio Dias", "52998224725"), hoje, dt.time(9, 0))

    corpo = _cliente(usuario).get(reverse("agenda:consultas")).content.decode()

    assert "Helena Costa" in corpo
    assert "Otávio Dias" not in corpo


def test_medico_sem_vinculo_nao_ve_nada(hoje: dt.date, medica: Medico) -> None:
    """O caso que separa permissão de decoração: o default é o fechado."""
    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))

    usuario = _usuario("sem_vinculo", "MEDICO")  # nenhum `Medico` aponta para ele
    corpo = _cliente(usuario).get(reverse("agenda:consultas")).content.decode()

    assert "Helena Costa" not in corpo


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------


def test_filtro_de_origem_recorta_a_listagem(hoje: dt.date, medica: Medico) -> None:
    _consulta(
        medica,
        _paciente("Helena Costa", "11144477735"),
        hoje,
        dt.time(8, 0),
        origem=Consulta.Origem.CHAT,
    )
    _consulta(
        medica,
        _paciente("Otávio Dias", "52998224725"),
        hoje,
        dt.time(9, 0),
        origem=Consulta.Origem.RECEPCAO,
    )

    cliente = _cliente(_usuario("recepcao", "RECEPCAO"))
    corpo = cliente.get(reverse("agenda:consultas"), {"origem": "CHAT"}).content.decode()

    assert "Helena Costa" in corpo
    assert "Otávio Dias" not in corpo


def test_busca_encontra_por_paciente_e_por_medico(hoje: dt.date, medica: Medico) -> None:
    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))
    _consulta(medica, _paciente("Otávio Dias", "52998224725"), hoje, dt.time(9, 0))
    cliente = _cliente(_usuario("recepcao", "RECEPCAO"))

    por_paciente = cliente.get(reverse("agenda:consultas"), {"q": "helena"}).content.decode()
    assert "Helena Costa" in por_paciente
    assert "Otávio Dias" not in por_paciente

    # O nome do médico casa com as duas, então nenhuma some.
    por_medico = cliente.get(reverse("agenda:consultas"), {"q": "ribeiro"}).content.decode()
    assert "Helena Costa" in por_medico
    assert "Otávio Dias" in por_medico


def test_contagens_da_lateral_falam_do_dia_inteiro(hoje: dt.date, medica: Medico) -> None:
    """Filtrar por CHAT não pode zerar a contagem de RECEPCAO na lateral.

    Se zerasse, a barra deixaria de dizer para onde ir em seguida — e a
    implementação natural (contar sobre a lista já filtrada) faz exatamente
    isso.
    """
    _consulta(
        medica,
        _paciente("Helena Costa", "11144477735"),
        hoje,
        dt.time(8, 0),
        origem=Consulta.Origem.CHAT,
    )
    _consulta(
        medica,
        _paciente("Otávio Dias", "52998224725"),
        hoje,
        dt.time(9, 0),
        origem=Consulta.Origem.RECEPCAO,
    )

    cliente = _cliente(_usuario("recepcao", "RECEPCAO"))
    contexto = cliente.get(reverse("agenda:consultas"), {"origem": "CHAT"}).context

    grupo_origem = next(g for g in contexto["filtros"] if g["titulo"] == "Origem")
    contagens = {o["rotulo"]: o["contagem"] for o in grupo_origem["opcoes"]}

    assert contagens["Tudo"] == "02"
    assert contagens["Chatbot"] == "01"
    assert contagens["Recepção"] == "01"  # não zerou, apesar do filtro
    assert len(contexto["consultas"]) == 1  # mas a listagem, sim, recortou


def test_filtro_de_medico_conta_por_pk_e_nao_por_instancia(
    hoje: dt.date, medica: Medico, medico_outro: Medico
) -> None:
    """O parâmetro carrega uma pk; ``Consulta.medico`` é a instância.

    Comparar os dois direto devolveria zero em toda linha — silenciosamente.
    """
    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))
    _consulta(medico_outro, _paciente("Otávio Dias", "52998224725"), hoje, dt.time(9, 0))

    contexto = _cliente(_usuario("recepcao", "RECEPCAO")).get(reverse("agenda:consultas")).context
    grupo_medico = next(g for g in contexto["filtros"] if g["titulo"] == "Médico")
    contagens = {o["rotulo"]: o["contagem"] for o in grupo_medico["opcoes"]}

    assert contagens["Ana Ribeiro"] == "01"
    assert contagens["Bruno Carvalho"] == "01"


@pytest.mark.parametrize("valor", ["abacaxi", "", "-5"])
def test_dia_ilegivel_ou_negativo_cai_em_hoje(hoje: dt.date, medica: Medico, valor: str) -> None:
    """Entrada que não é índice válido volta para o dia corrente."""
    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))

    resposta = _cliente(_usuario("recepcao", "RECEPCAO")).get(
        reverse("agenda:consultas"), {"dia": valor}
    )

    assert resposta.status_code == 200
    assert resposta.context["abas"][0]["ativa"] is True
    assert "Helena Costa" in resposta.content.decode()


@pytest.mark.parametrize("valor", ["3", "999", "99999999"])
def test_dia_alto_e_preso_na_janela_e_nao_vira_offset_de_data(
    hoje: dt.date, medica: Medico, valor: str
) -> None:
    """`?dia=999` não pode virar "hoje + 999 dias".

    O valor é preso na última aba, não rejeitado: prender mantém a tela
    utilizável, e o que importa aqui é que nenhum inteiro da querystring vire
    deslocamento de data arbitrário.
    """
    _consulta(medica, _paciente("Helena Costa", "11144477735"), hoje, dt.time(8, 0))

    resposta = _cliente(_usuario("recepcao", "RECEPCAO")).get(
        reverse("agenda:consultas"), {"dia": valor}
    )

    assert resposta.status_code == 200
    ativas = [a["indice"] for a in resposta.context["abas"] if a["ativa"]]
    assert ativas == [DIAS_NA_REGUA - 1]


# ---------------------------------------------------------------------------
# Custo
# ---------------------------------------------------------------------------


def test_a_grade_nao_cresce_em_queries_com_as_consultas(hoje: dt.date, medica: Medico) -> None:
    """N+1 na tela que fica aberta o dia inteiro é o defeito caro aqui."""
    cliente = _cliente(_usuario("recepcao", "RECEPCAO"))
    url = reverse("agenda:consultas")

    _consulta(medica, _paciente("Paciente 1", "11144477735"), hoje, dt.time(8, 0))
    with CaptureQueriesContext(connection) as uma:
        cliente.get(url)

    for indice, (cpf, hora) in enumerate(
        [
            ("52998224725", dt.time(9, 0)),
            ("16899535009", dt.time(9, 30)),
            ("64502882050", dt.time(10, 0)),
            ("28625587887", dt.time(10, 30)),
        ],
        start=2,
    ):
        _consulta(medica, _paciente(f"Paciente {indice}", cpf), hoje, hora)

    with CaptureQueriesContext(connection) as cinco:
        cliente.get(url)

    assert len(cinco) == len(uma), (
        f"a grade fez {len(cinco)} queries com 5 consultas contra {len(uma)} com 1 — "
        "o select_related da view caiu"
    )

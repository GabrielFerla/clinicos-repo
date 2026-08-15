"""Testes do Admin do prontuário — o que é editável e o que não é.

O ponto destes testes é uma coisa só: **``Evolucao`` e ``LogAcesso`` não podem
oferecer add, change nem delete**. Em ``Evolucao`` isso não é preferência de
UX — o trigger PL/SQL ``TRG_EVOLUCAO_IMUTAVEL`` `[S1-10]` recusa ``UPDATE`` e
``DELETE`` com ``ORA-20001``, então uma tela editável não corromperia o
prontuário: produziria erro 500 na cara de quem tentasse. Como a suíte roda em
SQLite (onde o trigger não existe), é justamente aqui que a proteção precisa
ser verificada — no Oracle o banco avisaria; no SQLite, ninguém avisaria.

As permissões são checadas nos dois níveis em que importam: na API do
``ModelAdmin`` (que também governa as ações em massa) e no HTTP (a URL de
inclusão tem que responder 403, não renderizar um formulário).
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.crm.models import Medico, Paciente
from apps.prontuario.models import Evolucao, LogAcesso, Prontuario

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client_logado() -> Client:
    usuario = get_user_model().objects.create_superuser(
        username="medico_admin",
        email="medico@example.com",
        password="senha-de-teste",  # noqa: S106
    )
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


@pytest.fixture
def paciente() -> Paciente:
    p = Paciente(nome="Joana Prado", data_nascimento=dt.date(1980, 5, 17))
    p.definir_cpf("12345678909")
    p.save()
    return p


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


@pytest.fixture
def prontuario(paciente: Paciente) -> Prontuario:
    return Prontuario.objects.create(paciente=paciente)


@pytest.fixture
def evolucao(prontuario: Prontuario, medica: Medico) -> Evolucao:
    return Evolucao.objects.create(
        prontuario=prontuario,
        medico=medica,
        texto="Acuidade visual 20/20 em ambos os olhos.",
    )


@pytest.fixture
def log(paciente: Paciente) -> LogAcesso:
    usuario = get_user_model().objects.create_user(
        username="recepcao",
        password="senha-de-teste",  # noqa: S106
    )
    return LogAcesso.objects.create(
        usuario=usuario, paciente=paciente, acao=LogAcesso.Acao.VISUALIZOU, ip="192.0.2.10"
    )


# ---------------------------------------------------------------------------
# Prontuario — editável
# ---------------------------------------------------------------------------


def test_listagem_de_prontuarios_carrega(
    admin_client_logado: Client, prontuario: Prontuario
) -> None:
    resposta = admin_client_logado.get(reverse("admin:prontuario_prontuario_changelist"))

    assert resposta.status_code == 200
    assert "Joana Prado" in resposta.content.decode()


def test_prontuario_mostra_a_contagem_de_evolucoes(
    admin_client_logado: Client, evolucao: Evolucao
) -> None:
    resposta = admin_client_logado.get(reverse("admin:prontuario_prontuario_changelist"))

    assert list(resposta.context["cl"].queryset)[0]._total_evolucoes == 1


def test_prontuario_pode_ser_criado_pelo_admin(admin_client_logado: Client) -> None:
    """O agregador é a única das três telas com escrita pela mão humana."""
    resposta = admin_client_logado.get(reverse("admin:prontuario_prontuario_add"))
    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# Evolucao — somente leitura (trigger TRG_EVOLUCAO_IMUTAVEL)
# ---------------------------------------------------------------------------


def test_evolucao_nao_oferece_inclusao_alteracao_nem_exclusao(evolucao: Evolucao) -> None:
    admin_de_evolucao = site._registry[Evolucao]
    requisicao = None  # as três permissões são negadas independentemente da request

    assert admin_de_evolucao.has_add_permission(requisicao) is False
    assert admin_de_evolucao.has_change_permission(requisicao, evolucao) is False
    assert admin_de_evolucao.has_delete_permission(requisicao, evolucao) is False


def test_evolucao_tem_todos_os_campos_em_readonly(evolucao: Evolucao) -> None:
    """Nem a tela de detalhe pode oferecer um campo editável."""
    admin_de_evolucao = site._registry[Evolucao]
    readonly = admin_de_evolucao.get_readonly_fields(None, evolucao)

    concretos = {campo.name for campo in Evolucao._meta.fields}
    assert set(readonly) == concretos


def test_url_de_inclusao_de_evolucao_e_negada(admin_client_logado: Client) -> None:
    resposta = admin_client_logado.get(reverse("admin:prontuario_evolucao_add"))
    assert resposta.status_code == 403


def test_post_de_alteracao_de_evolucao_e_negado(
    admin_client_logado: Client, evolucao: Evolucao
) -> None:
    url = reverse("admin:prontuario_evolucao_change", args=[evolucao.pk])

    resposta = admin_client_logado.post(url, {"texto": "Texto adulterado."})

    assert resposta.status_code == 403
    evolucao.refresh_from_db()
    assert evolucao.texto == "Acuidade visual 20/20 em ambos os olhos."


def test_listagem_de_evolucoes_carrega(admin_client_logado: Client, evolucao: Evolucao) -> None:
    resposta = admin_client_logado.get(reverse("admin:prontuario_evolucao_changelist"))

    assert resposta.status_code == 200
    assert "Ana Ribeiro" in resposta.content.decode()


def test_texto_clinico_fica_fora_da_busca() -> None:
    """``TextField`` vira ``NCLOB`` no Oracle — não entra em ``WHERE``."""
    assert "texto" not in site._registry[Evolucao].search_fields


def test_busca_de_evolucao_por_paciente(admin_client_logado: Client, evolucao: Evolucao) -> None:
    resposta = admin_client_logado.get(
        reverse("admin:prontuario_evolucao_changelist"), {"q": "Joana"}
    )

    assert list(resposta.context["cl"].queryset) == [evolucao]


# ---------------------------------------------------------------------------
# LogAcesso — somente leitura (auditoria LGPD)
# ---------------------------------------------------------------------------


def test_log_de_acesso_nao_oferece_inclusao_alteracao_nem_exclusao(log: LogAcesso) -> None:
    admin_do_log = site._registry[LogAcesso]

    assert admin_do_log.has_add_permission(None) is False
    assert admin_do_log.has_change_permission(None, log) is False
    assert admin_do_log.has_delete_permission(None, log) is False


def test_log_de_acesso_tem_todos_os_campos_em_readonly(log: LogAcesso) -> None:
    readonly = site._registry[LogAcesso].get_readonly_fields(None, log)
    assert set(readonly) == {campo.name for campo in LogAcesso._meta.fields}


def test_listagem_de_logs_carrega(admin_client_logado: Client, log: LogAcesso) -> None:
    resposta = admin_client_logado.get(reverse("admin:prontuario_logacesso_changelist"))
    corpo = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Joana Prado" in corpo
    assert "192.0.2.10" in corpo


def test_busca_de_log_pelo_paciente_responde_a_pergunta_do_titular(
    admin_client_logado: Client, log: LogAcesso
) -> None:
    """“Quem acessou meus dados?” é a pergunta que a trilha existe para responder."""
    resposta = admin_client_logado.get(
        reverse("admin:prontuario_logacesso_changelist"), {"q": "Joana"}
    )

    assert list(resposta.context["cl"].queryset) == [log]

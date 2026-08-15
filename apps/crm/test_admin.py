"""Testes do Admin do CRM — cadastro de paciente `[S2-9]` e funil de leads `[S5-23]`.

O Admin é o produto no MVP1 (ADR-0005), então o que estes testes cobrem não é
"configuração de tela": é o **único caminho** pelo qual um CPF entra no
ClinicOS. Três garantias concentram o valor:

* CPF com dígito verificador errado não é aceito — nem por engano de digitação,
  nem por CPF inventado;
* CPF já cadastrado é recusado com mensagem, e não com ``IntegrityError``
  virando erro 500 na cara da recepção;
* o que chega ao banco passou por ``Paciente.definir_cpf`` — ou seja, cifrado e
  hasheado de forma coerente, nunca em claro.

Rodam em SQLite, como o resto da suíte. A chave e o pepper vêm dos defaults
descartáveis do ``conftest.py`` da raiz.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.crm.admin import PacienteAdminForm
from apps.crm.models import Especialidade, Lead, Paciente

pytestmark = pytest.mark.django_db

CPF_VALIDO = "12345678909"
CPF_VALIDO_COM_MASCARA = "123.456.789-09"
OUTRO_CPF_VALIDO = "98765432100"
CPF_DV_INVALIDO = "12345678900"  # o segundo verificador correto seria 9


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _dados_do_form(**overrides: Any) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "nome": "Joana Prado",
        "cpf": CPF_VALIDO,
        "data_nascimento": "17/05/1980",
        "email": "",
        "telefone": "",
        "ativo": "on",
    }
    dados.update(overrides)
    return dados


def _paciente(nome: str = "Paciente Existente", cpf: str = CPF_VALIDO) -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=dt.date(1975, 3, 9))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


@pytest.fixture
def admin_client_logado() -> Client:
    """Cliente autenticado como superusuário — o perfil da recepção no MVP1."""
    usuario = get_user_model().objects.create_superuser(
        username="recepcao_admin",
        email="recepcao@example.com",
        password="senha-de-teste",  # noqa: S106
    )
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


# ---------------------------------------------------------------------------
# PacienteAdminForm — validação do CPF
# ---------------------------------------------------------------------------


def test_form_recusa_cpf_com_digito_verificador_invalido() -> None:
    form = PacienteAdminForm(data=_dados_do_form(cpf=CPF_DV_INVALIDO))

    assert not form.is_valid()
    assert "cpf" in form.errors
    assert "verificadores" in form.errors["cpf"][0]
    assert Paciente.objects.count() == 0


@pytest.mark.parametrize("cpf", ["11111111111", "00000000000"])
def test_form_recusa_cpf_de_digitos_repetidos(cpf: str) -> None:
    """Passam na aritmética dos verificadores; não são CPF de ninguém."""
    form = PacienteAdminForm(data=_dados_do_form(cpf=cpf))
    assert not form.is_valid()
    assert "cpf" in form.errors


@pytest.mark.parametrize("cpf", ["123", "1234567890123", "abc.def.ghi-jk"])
def test_form_recusa_cpf_com_quantidade_de_digitos_errada(cpf: str) -> None:
    form = PacienteAdminForm(data=_dados_do_form(cpf=cpf))
    assert not form.is_valid()
    assert "cpf" in form.errors


def test_form_exige_cpf_na_criacao() -> None:
    form = PacienteAdminForm(data=_dados_do_form(cpf=""))
    assert not form.is_valid()
    assert "cpf" in form.errors


def test_form_recusa_cpf_ja_cadastrado() -> None:
    existente = _paciente(nome="Joana Prado")

    form = PacienteAdminForm(data=_dados_do_form(nome="Homônima", cpf=CPF_VALIDO))

    assert not form.is_valid()
    assert existente.nome in form.errors["cpf"][0]
    assert Paciente.objects.count() == 1


def test_form_detecta_duplicidade_mesmo_com_mascara_diferente() -> None:
    """A busca é por hash do CPF normalizado — a pontuação não disfarça nada."""
    _paciente()

    form = PacienteAdminForm(data=_dados_do_form(cpf=CPF_VALIDO_COM_MASCARA))

    assert not form.is_valid()
    assert "cpf" in form.errors


# ---------------------------------------------------------------------------
# PacienteAdminForm — gravação
# ---------------------------------------------------------------------------


def test_cadastro_valido_grava_cpf_cifrado_e_hash_coerentes() -> None:
    form = PacienteAdminForm(data=_dados_do_form())
    assert form.is_valid(), form.errors

    paciente = form.save()

    # O que a property devolve são os dígitos originais...
    assert paciente.cpf == CPF_VALIDO
    # ...e o hash é o mesmo que a busca calcula, o que prova que as duas
    # colunas derivadas saíram do mesmo número.
    assert Paciente.objects.buscar_por_cpf(CPF_VALIDO).get() == paciente
    assert len(paciente.cpf_hash) == 64
    assert paciente.cpf_cifrado and paciente.cpf_cifrado != CPF_VALIDO


def test_cadastro_aceita_cpf_com_mascara_e_normaliza() -> None:
    form = PacienteAdminForm(data=_dados_do_form(cpf=CPF_VALIDO_COM_MASCARA))
    assert form.is_valid(), form.errors

    paciente = form.save()

    assert paciente.cpf == CPF_VALIDO


def test_form_nao_expoe_as_colunas_derivadas() -> None:
    """``cpf_cifrado``/``cpf_hash`` editáveis permitiriam gravar hash de um CPF
    e ciphertext de outro — bug silencioso e irreparável depois do INSERT."""
    form = PacienteAdminForm()
    assert "cpf_cifrado" not in form.fields
    assert "cpf_hash" not in form.fields


# ---------------------------------------------------------------------------
# PacienteAdminForm — edição
# ---------------------------------------------------------------------------


def test_edicao_com_cpf_em_branco_mantem_o_cpf_atual() -> None:
    paciente = _paciente(nome="Joana Prado")
    hash_original = paciente.cpf_hash

    form = PacienteAdminForm(
        data=_dados_do_form(nome="Joana Prado Silva", cpf=""),
        instance=paciente,
    )
    assert form.is_valid(), form.errors
    salvo = form.save()

    assert salvo.nome == "Joana Prado Silva"
    assert salvo.cpf_hash == hash_original
    assert salvo.cpf == CPF_VALIDO


def test_edicao_com_cpf_novo_regrava_as_duas_colunas() -> None:
    paciente = _paciente()

    form = PacienteAdminForm(data=_dados_do_form(cpf=OUTRO_CPF_VALIDO), instance=paciente)
    assert form.is_valid(), form.errors
    salvo = form.save()

    assert salvo.cpf == OUTRO_CPF_VALIDO
    assert Paciente.objects.buscar_por_cpf(OUTRO_CPF_VALIDO).get() == salvo
    assert not Paciente.objects.buscar_por_cpf(CPF_VALIDO).exists()


def test_edicao_aceita_o_proprio_cpf_redigitado() -> None:
    """A checagem de duplicidade exclui o próprio registro — senão nenhuma
    edição que redigitasse o CPF passaria."""
    paciente = _paciente()

    form = PacienteAdminForm(data=_dados_do_form(cpf=CPF_VALIDO), instance=paciente)

    assert form.is_valid(), form.errors


def test_edicao_recusa_cpf_de_outro_paciente() -> None:
    _paciente(nome="Primeira", cpf=CPF_VALIDO)
    segunda = _paciente(nome="Segunda", cpf=OUTRO_CPF_VALIDO)

    form = PacienteAdminForm(data=_dados_do_form(nome="Segunda", cpf=CPF_VALIDO), instance=segunda)

    assert not form.is_valid()
    assert "cpf" in form.errors


# ---------------------------------------------------------------------------
# Listagem de pacientes — busca por CPF e mascaramento
# ---------------------------------------------------------------------------


def test_busca_por_cpf_encontra_o_paciente_na_listagem(admin_client_logado: Client) -> None:
    """A demo da sprint: a recepção digita o CPF informado ao telefone e acha."""
    paciente = _paciente(nome="Joana Prado")
    _paciente(nome="Outro Qualquer", cpf=OUTRO_CPF_VALIDO)

    url = reverse("admin:crm_paciente_changelist")
    resposta = admin_client_logado.get(url, {"q": CPF_VALIDO})

    assert resposta.status_code == 200
    assert list(resposta.context["cl"].queryset) == [paciente]


def test_busca_por_cpf_aceita_mascara(admin_client_logado: Client) -> None:
    paciente = _paciente()

    resposta = admin_client_logado.get(
        reverse("admin:crm_paciente_changelist"), {"q": CPF_VALIDO_COM_MASCARA}
    )

    assert list(resposta.context["cl"].queryset) == [paciente]


def test_busca_por_nome_continua_funcionando(admin_client_logado: Client) -> None:
    """Termo que não tem 11 dígitos cai no comportamento padrão."""
    paciente = _paciente(nome="Joana Prado")
    _paciente(nome="Outro Qualquer", cpf=OUTRO_CPF_VALIDO)

    resposta = admin_client_logado.get(reverse("admin:crm_paciente_changelist"), {"q": "Joana"})

    assert list(resposta.context["cl"].queryset) == [paciente]


def test_busca_por_cpf_inexistente_nao_devolve_nada(admin_client_logado: Client) -> None:
    _paciente()

    resposta = admin_client_logado.get(
        reverse("admin:crm_paciente_changelist"), {"q": OUTRO_CPF_VALIDO}
    )

    assert list(resposta.context["cl"].queryset) == []


def test_listagem_de_pacientes_mostra_o_cpf_mascarado(admin_client_logado: Client) -> None:
    """Requisito de LGPD: o número em claro não aparece em listagem."""
    _paciente()

    resposta = admin_client_logado.get(reverse("admin:crm_paciente_changelist"))
    corpo = resposta.content.decode()

    assert resposta.status_code == 200
    assert "***.***.789-09" in corpo
    assert CPF_VALIDO not in corpo
    assert CPF_VALIDO_COM_MASCARA not in corpo


def test_cadastro_pelo_admin_grava_o_cpf_cifrado(admin_client_logado: Client) -> None:
    """Fluxo ponta a ponta: POST na tela de cadastro → linha cifrada no banco."""
    resposta = admin_client_logado.post(
        reverse("admin:crm_paciente_add"), _dados_do_form(), follow=True
    )

    assert resposta.status_code == 200
    paciente = Paciente.objects.get(nome="Joana Prado")
    assert paciente.cpf == CPF_VALIDO
    assert CPF_VALIDO not in paciente.cpf_cifrado


# ---------------------------------------------------------------------------
# Funil de leads [S5-23]
# ---------------------------------------------------------------------------


def test_listagem_de_leads_carrega(admin_client_logado: Client) -> None:
    Especialidade.objects.create(nome="Retina", slug="retina")
    Lead.objects.create(nome="Marina Souza", etapa=Lead.Etapa.NOVO)

    resposta = admin_client_logado.get(reverse("admin:crm_lead_changelist"))

    assert resposta.status_code == 200
    assert "Marina Souza" in resposta.content.decode()


def test_funil_move_lead_de_etapa_direto_na_listagem(admin_client_logado: Client) -> None:
    """``list_editable`` é a feature da S5-23, não um detalhe de configuração."""
    lead = Lead.objects.create(nome="Marina Souza", etapa=Lead.Etapa.NOVO)

    resposta = admin_client_logado.post(
        reverse("admin:crm_lead_changelist"),
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(lead.pk),
            "form-0-etapa": Lead.Etapa.QUALIFICADO,
            "_save": "Salvar",
        },
    )

    assert resposta.status_code == 302
    lead.refresh_from_db()
    assert lead.etapa == Lead.Etapa.QUALIFICADO


def test_filtro_por_etapa_restringe_o_funil(admin_client_logado: Client) -> None:
    novo = Lead.objects.create(nome="Recém-chegado", etapa=Lead.Etapa.NOVO)
    Lead.objects.create(nome="Já agendado", etapa=Lead.Etapa.AGENDADO)

    resposta = admin_client_logado.get(
        reverse("admin:crm_lead_changelist"), {"etapa__exact": Lead.Etapa.NOVO}
    )

    assert list(resposta.context["cl"].queryset) == [novo]


def test_busca_de_lead_por_telefone(admin_client_logado: Client) -> None:
    lead = Lead.objects.create(nome="Marina Souza", telefone="51999990000")
    Lead.objects.create(nome="Outro", telefone="51988887777")

    resposta = admin_client_logado.get(reverse("admin:crm_lead_changelist"), {"q": "51999990000"})

    assert list(resposta.context["cl"].queryset) == [lead]

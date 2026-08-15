"""Permissões por perfil no Admin `[S2-10]` `[S2-18]`.

Os testes moram no ``core`` porque a regra mora no ``core``: quem decide o
recorte é ``Usuario.perfil``, e o :class:`~apps.core.admin.RestritoAoMedicoMixin`
é aplicado a três Admins de três apps diferentes. Espalhar as asserções por
``crm``, ``agenda`` e ``prontuario`` daria três meias-verdades — o valor está
justamente em ver as três telas concordando entre si.

O que aqui é requisito, e não trivialidade
------------------------------------------
* **Médico sem ``Medico`` vinculado vê lista vazia.** É o caso que separa uma
  permissão de uma decoração: um perfil ``MEDICO`` recém-criado, ainda sem
  vínculo, não pode "cair no else" e enxergar a clínica inteira. O default é o
  fechado.
* **Acesso direto por URL é barrado** `[S2-18]`. O DoD da sprint fala em 403; o
  Django Admin responde 302 para o index com "não existe", que é *mais*
  restritivo — o 403 confirmaria a existência do id ao intruso, e o 302 não
  distingue "existe mas não é seu" de "não existe". O teste aceita os dois e
  verifica o que importa: o objeto alheio não aparece na resposta.
* **A restrição vale para o autocomplete**, não só para o changelist. É o
  caminho lateral que costuma sobrar: a listagem protegida e a busca do
  ``ConsultaAdmin`` devolvendo o nome de qualquer paciente da base.

Rodam em SQLite, como o resto da suíte.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.agenda.models import AgendaSlot, Consulta
from apps.crm.models import Medico, Paciente
from apps.prontuario.models import Prontuario

pytestmark = pytest.mark.django_db

DIA = dt.date(2026, 9, 15)
SENHA = "senha-de-teste"  # noqa: S105


# ---------------------------------------------------------------------------
# Fixtures — dois médicos, um paciente cada, sem cruzamento
# ---------------------------------------------------------------------------


def _usuario(username: str, perfil: str, **extras: object):
    """Usuário de staff (o Admin exige ``is_staff``) com todas as permissões.

    ``is_superuser`` fica **fora** de propósito: superusuário pula o recorte por
    desenho, então testar com ele mediria nada. As permissões vêm de
    ``is_staff`` + ``user_permissions`` explícitas, para que o que estes testes
    exercitam seja o ``get_queryset``, e não a checagem de permissão do Django.
    """
    from django.contrib.auth.models import Permission

    usuario = get_user_model().objects.create_user(
        username=username,
        password=SENHA,
        perfil=perfil,
        is_staff=True,
        **extras,
    )
    usuario.user_permissions.set(Permission.objects.all())
    return usuario


def _cliente(usuario) -> Client:
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


def _paciente(nome: str, cpf: str) -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=dt.date(1985, 1, 20))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


def _consulta(medico: Medico, hora: dt.time, paciente: Paciente) -> Consulta:
    fim = (dt.datetime.combine(DIA, hora) + dt.timedelta(minutes=30)).time()
    slot = AgendaSlot.objects.create(
        medico=medico,
        data=DIA,
        hora_inicio=hora,
        hora_fim=fim,
        status=AgendaSlot.Status.RESERVADO,
    )
    return Consulta.objects.create(paciente=paciente, slot=slot, medico=medico)


class Cenario:
    """Duas agendas independentes: médico A com Joana, médico B com Carlos."""

    def __init__(self) -> None:
        self.usuario_a = _usuario("dra.ana", get_user_model().Perfil.MEDICO)
        self.usuario_b = _usuario("dr.bruno", get_user_model().Perfil.MEDICO)
        self.medico_a = Medico.objects.create(
            nome="Ana Ribeiro", crm_numero="11111", crm_uf="SP", usuario=self.usuario_a
        )
        self.medico_b = Medico.objects.create(
            nome="Bruno Salles", crm_numero="22222", crm_uf="SP", usuario=self.usuario_b
        )
        self.paciente_a = _paciente("Joana Prado", "12345678909")
        self.paciente_b = _paciente("Carlos Nunes", "98765432100")
        self.consulta_a = _consulta(self.medico_a, dt.time(9, 0), self.paciente_a)
        self.consulta_b = _consulta(self.medico_b, dt.time(10, 0), self.paciente_b)
        self.prontuario_a = Prontuario.objects.create(paciente=self.paciente_a)
        self.prontuario_b = Prontuario.objects.create(paciente=self.paciente_b)

        self.cliente_a = _cliente(self.usuario_a)
        self.cliente_b = _cliente(self.usuario_b)


@pytest.fixture
def cenario() -> Cenario:
    return Cenario()


def _pks(resposta) -> set[int]:
    """PKs visíveis no changelist, lidos do queryset e não do HTML."""
    return {obj.pk for obj in resposta.context["cl"].queryset}


# ---------------------------------------------------------------------------
# Consulta — o recorte direto
# ---------------------------------------------------------------------------


def test_medico_ve_a_propria_consulta_e_nao_a_do_colega(cenario: Cenario) -> None:
    resposta = cenario.cliente_a.get(reverse("admin:agenda_consulta_changelist"))

    assert resposta.status_code == 200
    assert _pks(resposta) == {cenario.consulta_a.pk}
    corpo = resposta.content.decode()
    assert "Joana Prado" in corpo
    assert "Carlos Nunes" not in corpo


def test_o_recorte_e_simetrico(cenario: Cenario) -> None:
    """O médico B enxerga o complemento exato do que o A enxerga."""
    resposta = cenario.cliente_b.get(reverse("admin:agenda_consulta_changelist"))

    assert _pks(resposta) == {cenario.consulta_b.pk}


def test_recepcao_ve_as_duas_consultas(cenario: Cenario) -> None:
    recepcao = _usuario("recepcao", get_user_model().Perfil.RECEPCAO)

    resposta = _cliente(recepcao).get(reverse("admin:agenda_consulta_changelist"))

    assert _pks(resposta) == {cenario.consulta_a.pk, cenario.consulta_b.pk}


def test_perfil_admin_ve_as_duas_consultas(cenario: Cenario) -> None:
    gestor = _usuario("gestor", get_user_model().Perfil.ADMIN)

    resposta = _cliente(gestor).get(reverse("admin:agenda_consulta_changelist"))

    assert _pks(resposta) == {cenario.consulta_a.pk, cenario.consulta_b.pk}


def test_superusuario_medico_continua_vendo_tudo(cenario: Cenario) -> None:
    """Um superusuário que também atende não pode perder o painel."""
    chefe = _usuario("chefe", get_user_model().Perfil.MEDICO, is_superuser=True)
    Medico.objects.create(nome="Chefe", crm_numero="33333", crm_uf="SP", usuario=chefe)

    resposta = _cliente(chefe).get(reverse("admin:agenda_consulta_changelist"))

    assert _pks(resposta) == {cenario.consulta_a.pk, cenario.consulta_b.pk}


def test_medico_sem_vinculo_nao_ve_nada(cenario: Cenario) -> None:
    """O caso perigoso: perfil MEDICO sem ``Medico`` associado.

    Se o recorte caísse no ``else``, este usuário — que pode ser qualquer conta
    recém-criada — enxergaria a clínica inteira.
    """
    orfao = _usuario("sem.vinculo", get_user_model().Perfil.MEDICO)
    cliente = _cliente(orfao)

    for url in (
        reverse("admin:agenda_consulta_changelist"),
        reverse("admin:crm_paciente_changelist"),
        reverse("admin:prontuario_prontuario_changelist"),
    ):
        resposta = cliente.get(url)
        assert resposta.status_code == 200, url
        assert _pks(resposta) == set(), url


# ---------------------------------------------------------------------------
# S2-18 — acesso direto por URL
# ---------------------------------------------------------------------------


def test_medico_nao_abre_a_consulta_do_colega_pela_url(cenario: Cenario) -> None:
    """`[S2-18]` — o item de DoD explícito da sprint.

    O ``get_object`` do ``ModelAdmin`` lê do mesmo queryset recortado, então o
    id alheio cai no caminho de "não existe". Confirmado, e não assumido.
    """
    url = reverse("admin:agenda_consulta_change", args=[cenario.consulta_b.pk])

    resposta = cenario.cliente_a.get(url)

    assert resposta.status_code in (302, 403)
    if resposta.status_code == 302:
        # Redireciona para fora da tela do objeto — não para ela mesma.
        assert not resposta["Location"].endswith(url)
    seguida = cenario.cliente_a.get(url, follow=True)
    assert "Carlos Nunes" not in seguida.content.decode()


def test_o_dono_abre_a_propria_consulta_pela_mesma_url(cenario: Cenario) -> None:
    """O contrapeso do teste acima: o 302 é do recorte, não de um bug de rota."""
    resposta = cenario.cliente_a.get(
        reverse("admin:agenda_consulta_change", args=[cenario.consulta_a.pk])
    )

    assert resposta.status_code == 200
    assert "Joana Prado" in resposta.content.decode()


def test_medico_nao_abre_o_paciente_alheio_pela_url(cenario: Cenario) -> None:
    url = reverse("admin:crm_paciente_change", args=[cenario.paciente_b.pk])

    resposta = cenario.cliente_a.get(url)

    assert resposta.status_code in (302, 403)
    assert "Carlos Nunes" not in cenario.cliente_a.get(url, follow=True).content.decode()


def test_medico_nao_abre_o_prontuario_alheio_pela_url(cenario: Cenario) -> None:
    url = reverse("admin:prontuario_prontuario_change", args=[cenario.prontuario_b.pk])

    resposta = cenario.cliente_a.get(url)

    assert resposta.status_code in (302, 403)
    assert "Carlos Nunes" not in cenario.cliente_a.get(url, follow=True).content.decode()


# ---------------------------------------------------------------------------
# Paciente e Prontuário — o recorte indireto
# ---------------------------------------------------------------------------


def test_medico_ve_so_os_pacientes_com_consulta_com_ele(cenario: Cenario) -> None:
    resposta = cenario.cliente_a.get(reverse("admin:crm_paciente_changelist"))

    assert _pks(resposta) == {cenario.paciente_a.pk}


def test_paciente_nunca_atendido_por_ninguem_some_das_duas_listas(cenario: Cenario) -> None:
    """Paciente sem consulta não pertence a médico nenhum — mas a recepção o vê."""
    avulso = _paciente("Sem Consulta", "11144477735")

    assert _pks(cenario.cliente_a.get(reverse("admin:crm_paciente_changelist"))) == {
        cenario.paciente_a.pk
    }
    recepcao = _usuario("recepcao2", get_user_model().Perfil.RECEPCAO)
    visiveis = _pks(_cliente(recepcao).get(reverse("admin:crm_paciente_changelist")))
    assert avulso.pk in visiveis


def test_paciente_aparece_uma_vez_so_com_varias_consultas(cenario: Cenario) -> None:
    """A subquery evita o duplicado que um join traria — sem precisar de DISTINCT."""
    _consulta(cenario.medico_a, dt.time(11, 0), cenario.paciente_a)
    _consulta(cenario.medico_a, dt.time(14, 0), cenario.paciente_a)

    resposta = cenario.cliente_a.get(reverse("admin:crm_paciente_changelist"))

    assert list(resposta.context["cl"].queryset) == [cenario.paciente_a]


def test_paciente_compartilhado_aparece_para_os_dois_medicos(cenario: Cenario) -> None:
    """Encaminhamento é rotina: o recorte é "tem consulta comigo", não "é meu"."""
    _consulta(cenario.medico_b, dt.time(15, 0), cenario.paciente_a)

    for cliente in (cenario.cliente_a, cenario.cliente_b):
        visiveis = _pks(cliente.get(reverse("admin:crm_paciente_changelist")))
        assert cenario.paciente_a.pk in visiveis


def test_medico_ve_so_o_prontuario_dos_proprios_pacientes(cenario: Cenario) -> None:
    resposta = cenario.cliente_a.get(reverse("admin:prontuario_prontuario_changelist"))

    assert _pks(resposta) == {cenario.prontuario_a.pk}


def test_recepcao_ve_os_dois_prontuarios(cenario: Cenario) -> None:
    recepcao = _usuario("recepcao3", get_user_model().Perfil.RECEPCAO)

    resposta = _cliente(recepcao).get(reverse("admin:prontuario_prontuario_changelist"))

    assert _pks(resposta) == {cenario.prontuario_a.pk, cenario.prontuario_b.pk}


# ---------------------------------------------------------------------------
# Caminhos laterais — busca e autocomplete
# ---------------------------------------------------------------------------


def test_busca_por_nome_nao_atravessa_o_recorte(cenario: Cenario) -> None:
    resposta = cenario.cliente_a.get(reverse("admin:crm_paciente_changelist"), {"q": "Carlos"})

    assert _pks(resposta) == set()


def test_busca_por_cpf_nao_atravessa_o_recorte(cenario: Cenario) -> None:
    """O atalho de CPF de ``PacienteAdmin.get_search_results`` filtra o queryset
    recebido — que já vem recortado —, e não o do manager."""
    resposta = cenario.cliente_a.get(
        reverse("admin:crm_paciente_changelist"), {"q": "987.654.321-00"}
    )

    assert _pks(resposta) == set()


def test_autocomplete_de_paciente_nao_vaza_nome_alheio(cenario: Cenario) -> None:
    """O caminho lateral: changelist protegido e autocomplete aberto."""
    resposta = cenario.cliente_a.get(
        reverse("admin:autocomplete"),
        {
            "term": "a",
            "app_label": "agenda",
            "model_name": "consulta",
            "field_name": "paciente",
        },
    )

    assert resposta.status_code == 200
    textos = [item["text"] for item in resposta.json()["results"]]
    assert textos == ["Joana Prado"]


# ---------------------------------------------------------------------------
# O vínculo em si
# ---------------------------------------------------------------------------


def test_medico_vinculado_devolve_none_sem_vinculo() -> None:
    from apps.core.admin import medico_vinculado

    solto = _usuario("solto", get_user_model().Perfil.MEDICO)

    assert medico_vinculado(solto) is None


def test_medico_vinculado_devolve_o_medico(cenario: Cenario) -> None:
    from apps.core.admin import medico_vinculado

    assert medico_vinculado(cenario.usuario_a) == cenario.medico_a


def test_apagar_o_usuario_preserva_o_medico(cenario: Cenario) -> None:
    """``SET_NULL``: o login some, o corpo clínico e o histórico ficam."""
    cenario.usuario_a.delete()
    cenario.medico_a.refresh_from_db()

    assert cenario.medico_a.usuario is None
    assert Consulta.objects.filter(pk=cenario.consulta_a.pk).exists()

"""Testes dos models do CRM (Bloco 1A do ``docs/CHAT_MVP.md``).

Cobrem o que o schema promete e o código sozinho não garante: unicidade
composta do CRM, unicidade do vínculo médico↔especialidade, e o ``on_delete``
de cada FK. Rodam em SQLite — as constraints testadas aqui são portáveis; as
que dependem de Oracle (``VECTOR``, PL/SQL) ficam sob ``@pytest.mark.oracle``.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.crm.models import Especialidade, Medico, MedicoEspecialidade

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def retina() -> Especialidade:
    return Especialidade.objects.create(nome="Retina", slug="retina")


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


# ---------------------------------------------------------------------------
# Especialidade
# ---------------------------------------------------------------------------


def test_especialidade_str_usa_o_nome(retina: Especialidade) -> None:
    assert str(retina) == "Retina"


def test_especialidade_nasce_ativa_e_datada(retina: Especialidade) -> None:
    assert retina.ativo is True
    assert retina.descricao == ""
    assert retina.criado_em is not None


def test_especialidade_nome_e_unico(retina: Especialidade) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Especialidade.objects.create(nome="Retina", slug="retina-2")


def test_especialidade_slug_e_unico(retina: Especialidade) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Especialidade.objects.create(nome="Retina Clínica", slug="retina")


def test_especialidade_ordena_por_nome() -> None:
    Especialidade.objects.create(nome="Glaucoma", slug="glaucoma")
    Especialidade.objects.create(nome="Catarata", slug="catarata")
    assert list(Especialidade.objects.values_list("nome", flat=True)) == ["Catarata", "Glaucoma"]


# ---------------------------------------------------------------------------
# Medico
# ---------------------------------------------------------------------------


def test_medico_str_inclui_crm_formatado(medica: Medico) -> None:
    assert medica.crm_completo == "12345/SP"
    assert str(medica) == "Ana Ribeiro (CRM 12345/SP)"


def test_medico_crm_e_unico_dentro_da_uf(medica: Medico) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Medico.objects.create(nome="Outro Médico", crm_numero="12345", crm_uf="SP")


def test_mesmo_numero_de_crm_em_ufs_diferentes_e_valido(medica: Medico) -> None:
    """A unicidade é composta de propósito: o CRM só é único por conselho estadual."""
    outro = Medico.objects.create(nome="Bruno Costa", crm_numero="12345", crm_uf="RJ")
    assert Medico.objects.count() == 2
    assert outro.crm_completo == "12345/RJ"


# ---------------------------------------------------------------------------
# MedicoEspecialidade
# ---------------------------------------------------------------------------


def test_vinculo_liga_os_dois_lados(medica: Medico, retina: Especialidade) -> None:
    MedicoEspecialidade.objects.create(medico=medica, especialidade=retina, principal=True)

    assert list(medica.especialidades.all()) == [retina]
    assert list(retina.medicos.all()) == [medica]


def test_vinculo_str_marca_a_principal(medica: Medico, retina: Especialidade) -> None:
    vinculo = MedicoEspecialidade.objects.create(
        medico=medica, especialidade=retina, principal=True
    )
    assert str(vinculo) == "Ana Ribeiro — Retina (principal)"

    vinculo.principal = False
    assert str(vinculo) == "Ana Ribeiro — Retina"


def test_vinculo_nao_pode_duplicar(medica: Medico, retina: Especialidade) -> None:
    MedicoEspecialidade.objects.create(medico=medica, especialidade=retina)
    with pytest.raises(IntegrityError), transaction.atomic():
        MedicoEspecialidade.objects.create(medico=medica, especialidade=retina)


def test_apagar_especialidade_com_vinculo_e_bloqueado(
    medica: Medico, retina: Especialidade
) -> None:
    """PROTECT: catálogo não some e leva o histórico do corpo clínico junto."""
    MedicoEspecialidade.objects.create(medico=medica, especialidade=retina)
    with pytest.raises(ProtectedError):
        retina.delete()


def test_apagar_medico_leva_os_vinculos(medica: Medico, retina: Especialidade) -> None:
    """CASCADE no lado do médico: o vínculo não existe sem ele."""
    MedicoEspecialidade.objects.create(medico=medica, especialidade=retina)
    medica.delete()

    assert MedicoEspecialidade.objects.count() == 0
    assert Especialidade.objects.filter(pk=retina.pk).exists()


# ---------------------------------------------------------------------------
# Convenções de schema (Oracle)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "tabela"),
    [
        (Especialidade, "ESPECIALIDADE"),
        (Medico, "MEDICO"),
        (MedicoEspecialidade, "MEDICO_ESPECIALIDADE"),
    ],
)
def test_tabelas_em_upper_snake_case(model: type, tabela: str) -> None:
    assert model._meta.db_table == tabela


@pytest.mark.parametrize("model", [Especialidade, Medico, MedicoEspecialidade])
def test_indices_e_constraints_tem_nome_explicito_e_curto(model: type) -> None:
    """Nome autogerado passa de 30 chars, o Oracle trunca, e o rollback quebra."""
    nomes = [c.name for c in model._meta.constraints] + [i.name for i in model._meta.indexes]
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"

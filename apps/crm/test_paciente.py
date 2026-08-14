"""Testes do model ``Paciente`` — o contrato de PII do ClinicOS (S1-8).

O que estes testes protegem não é comportamento de conveniência, é requisito
de LGPD: **em nenhuma coluna do banco pode haver CPF em claro**. Por isso o
teste central (``test_definir_cpf_nao_deixa_o_numero_em_claro_em_coluna_alguma``)
não checa um campo específico — varre a linha inteira, coluna por coluna, e
falha se os 11 dígitos aparecerem em qualquer uma. Assim, um campo novo que
vaze o CPF no futuro quebra o teste sem ninguém precisar lembrar de atualizá-lo.

Rodam em SQLite: cripto, hash e a constraint UNIQUE de ``cpf_hash`` são
portáveis. A chave e o pepper vêm dos defaults descartáveis do ``conftest.py``
da raiz.
"""

from __future__ import annotations

import datetime

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, connection, transaction
from django.test import override_settings

from apps.crm.models import Paciente

pytestmark = pytest.mark.django_db

CPF_LIMPO = "12345678909"
CPF_MASCARADO = "123.456.789-09"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _novo_paciente(nome: str = "Joana Prado", cpf: str = CPF_LIMPO) -> Paciente:
    paciente = Paciente(nome=nome, data_nascimento=datetime.date(1980, 5, 17))
    paciente.definir_cpf(cpf)
    paciente.save()
    return paciente


@pytest.fixture
def joana() -> Paciente:
    return _novo_paciente()


# ---------------------------------------------------------------------------
# definir_cpf: cifra, hasheia e nunca grava em claro
# ---------------------------------------------------------------------------


def test_definir_cpf_preenche_as_duas_colunas_derivadas(joana: Paciente) -> None:
    assert joana.cpf_cifrado
    assert len(joana.cpf_hash) == 64
    assert joana.cpf_cifrado != CPF_LIMPO


def test_definir_cpf_nao_salva_sozinho() -> None:
    """A persistência é decisão do caller — permite cadastro num único INSERT."""
    paciente = Paciente(nome="Sem Save", data_nascimento=datetime.date(1990, 1, 1))
    paciente.definir_cpf(CPF_LIMPO)

    assert paciente.pk is None
    assert Paciente.objects.count() == 0


def test_definir_cpf_nao_deixa_o_numero_em_claro_em_coluna_alguma(joana: Paciente) -> None:
    """Varre a linha inteira no banco: nenhum campo pode conter os 11 dígitos.

    Lê via SQL cru de propósito — o ORM devolveria o que o model *diz* que
    guarda, e o ponto aqui é auditar o que o banco de fato tem.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM PACIENTE WHERE ID = %s", [joana.pk])
        colunas = [c[0] for c in cursor.description]
        linha = cursor.fetchone()

    for coluna, valor in zip(colunas, linha, strict=True):
        texto = str(valor)
        assert CPF_LIMPO not in texto, f"CPF em claro na coluna {coluna}"
        assert CPF_MASCARADO not in texto, f"CPF em claro na coluna {coluna}"


def test_cpf_faz_round_trip_pela_property(joana: Paciente) -> None:
    recarregado = Paciente.objects.get(pk=joana.pk)
    assert recarregado.cpf == CPF_LIMPO


def test_cpf_e_somente_leitura(joana: Paciente) -> None:
    """Sem setter: o único caminho de escrita é ``definir_cpf``."""
    with pytest.raises(AttributeError):
        joana.cpf = "98765432100"


def test_cpf_de_paciente_sem_cpf_e_string_vazia() -> None:
    paciente = Paciente(nome="Sem CPF", data_nascimento=datetime.date(2000, 3, 3))
    assert paciente.cpf == ""
    assert paciente.cpf_mascarado == ""


def test_cpf_mascarado_esconde_os_primeiros_digitos(joana: Paciente) -> None:
    assert joana.cpf_mascarado == "***.***.789-09"


def test_cifragem_usa_nonce_novo_a_cada_chamada() -> None:
    """Mesmo CPF, tokens distintos — evita correlação entre linhas no banco."""
    um = Paciente(nome="A", data_nascimento=datetime.date(1970, 1, 1))
    outro = Paciente(nome="B", data_nascimento=datetime.date(1970, 1, 1))
    um.definir_cpf(CPF_LIMPO)
    outro.definir_cpf(CPF_LIMPO)

    assert um.cpf_cifrado != outro.cpf_cifrado
    # O hash, ao contrário, é determinístico — é o que torna a busca possível.
    assert um.cpf_hash == outro.cpf_hash


def test_definir_cpf_recusa_valor_invalido() -> None:
    paciente = Paciente(nome="Inválido", data_nascimento=datetime.date(1970, 1, 1))
    with pytest.raises(ValueError):
        paciente.definir_cpf("123")

    assert paciente.cpf_cifrado == ""
    assert paciente.cpf_hash == ""


# ---------------------------------------------------------------------------
# Máscara: entrada formatada e entrada limpa são o mesmo CPF
# ---------------------------------------------------------------------------


def test_cpf_com_e_sem_mascara_geram_o_mesmo_hash() -> None:
    limpo = Paciente(nome="Limpo", data_nascimento=datetime.date(1970, 1, 1))
    formatado = Paciente(nome="Formatado", data_nascimento=datetime.date(1970, 1, 1))
    limpo.definir_cpf(CPF_LIMPO)
    formatado.definir_cpf(CPF_MASCARADO)

    assert limpo.cpf_hash == formatado.cpf_hash
    # E o valor decifrado também é normalizado, não a string digitada.
    assert formatado.cpf == CPF_LIMPO


# ---------------------------------------------------------------------------
# PacienteManager.buscar_por_cpf
# ---------------------------------------------------------------------------


def test_buscar_por_cpf_encontra_sem_descriptografar(joana: Paciente) -> None:
    assert Paciente.objects.buscar_por_cpf(CPF_LIMPO).get() == joana


def test_buscar_por_cpf_aceita_mascara(joana: Paciente) -> None:
    assert Paciente.objects.buscar_por_cpf(CPF_MASCARADO).get() == joana


def test_buscar_por_cpf_nao_encontra_cpf_ausente(joana: Paciente) -> None:
    assert not Paciente.objects.buscar_por_cpf("98765432100").exists()


def test_buscar_por_cpf_devolve_queryset_encadeavel(joana: Paciente) -> None:
    """Soft delete não é aplicado na busca: arquivado ainda tem que ser achável."""
    joana.ativo = False
    joana.save(update_fields=["ativo"])

    assert Paciente.objects.buscar_por_cpf(CPF_LIMPO).exists()
    assert not Paciente.objects.buscar_por_cpf(CPF_LIMPO).filter(ativo=True).exists()


def test_buscar_por_cpf_recusa_cpf_invalido() -> None:
    with pytest.raises(ValueError):
        Paciente.objects.buscar_por_cpf("abc")


# ---------------------------------------------------------------------------
# Unicidade e soft delete
# ---------------------------------------------------------------------------


def test_cpf_duplicado_e_recusado_pela_constraint(joana: Paciente) -> None:
    duplicado = Paciente(nome="Homônima", data_nascimento=datetime.date(1991, 9, 9))
    duplicado.definir_cpf(CPF_MASCARADO)  # mesmo CPF, digitado com máscara

    with pytest.raises(IntegrityError), transaction.atomic():
        duplicado.save()


def test_paciente_nasce_ativo_e_datado(joana: Paciente) -> None:
    assert joana.ativo is True
    assert joana.criado_em is not None
    assert joana.atualizado_em is not None
    assert joana.email == ""
    assert joana.telefone == ""


def test_soft_delete_preserva_a_linha(joana: Paciente) -> None:
    """Retenção CFM de 20 anos: `ativo=False`, nunca DELETE físico."""
    joana.ativo = False
    joana.save(update_fields=["ativo"])

    recarregado = Paciente.objects.get(pk=joana.pk)
    assert recarregado.ativo is False
    assert recarregado.cpf == CPF_LIMPO
    assert Paciente.objects.count() == 1


def test_str_usa_o_nome(joana: Paciente) -> None:
    assert str(joana) == "Joana Prado"


# ---------------------------------------------------------------------------
# Settings ausentes: ImproperlyConfigured, não TypeError obscuro
# ---------------------------------------------------------------------------


@override_settings(CPF_ENCRYPTION_KEY=None)
def test_sem_chave_de_cifragem_falha_com_mensagem_clara() -> None:
    paciente = Paciente(nome="X", data_nascimento=datetime.date(1970, 1, 1))
    with pytest.raises(ImproperlyConfigured, match="CPF_ENCRYPTION_KEY"):
        paciente.definir_cpf(CPF_LIMPO)


@override_settings(CPF_HASH_PEPPER=None)
def test_sem_pepper_falha_com_mensagem_clara() -> None:
    paciente = Paciente(nome="X", data_nascimento=datetime.date(1970, 1, 1))
    with pytest.raises(ImproperlyConfigured, match="CPF_HASH_PEPPER"):
        paciente.definir_cpf(CPF_LIMPO)


@override_settings(CPF_HASH_PEPPER=None)
def test_sem_pepper_a_busca_tambem_falha_de_forma_clara() -> None:
    with pytest.raises(ImproperlyConfigured, match="CPF_HASH_PEPPER"):
        Paciente.objects.buscar_por_cpf(CPF_LIMPO)


@override_settings(CPF_ENCRYPTION_KEY="isto-nao-e-uma-chave-aes-256")
def test_chave_malformada_vira_improperly_configured_e_nao_valueerror() -> None:
    """`binascii.Error`/`InvalidKeyError` no meio de um cadastro não diz o que fazer."""
    paciente = Paciente(nome="X", data_nascimento=datetime.date(1970, 1, 1))
    with pytest.raises(ImproperlyConfigured, match="CPF_ENCRYPTION_KEY"):
        paciente.definir_cpf(CPF_LIMPO)


@override_settings(CPF_HASH_PEPPER="curto")
def test_pepper_curto_demais_vira_improperly_configured() -> None:
    paciente = Paciente(nome="X", data_nascimento=datetime.date(1970, 1, 1))
    with pytest.raises(ImproperlyConfigured, match="16"):
        paciente.definir_cpf(CPF_LIMPO)


@override_settings(CPF_ENCRYPTION_KEY=None)
def test_leitura_do_cpf_sem_chave_tambem_falha_de_forma_clara() -> None:
    """A property não pode devolver lixo nem estourar `TypeError` se a chave sumir."""
    paciente = Paciente(nome="X", data_nascimento=datetime.date(1970, 1, 1))
    paciente.cpf_cifrado = "token-qualquer"
    with pytest.raises(ImproperlyConfigured, match="CPF_ENCRYPTION_KEY"):
        _ = paciente.cpf


# ---------------------------------------------------------------------------
# Convenções de schema (Oracle)
# ---------------------------------------------------------------------------


def test_tabela_em_upper_snake_case() -> None:
    assert Paciente._meta.db_table == "PACIENTE"


def test_indices_e_constraints_tem_nome_explicito_e_curto() -> None:
    """Nome autogerado passa de 30 chars, o Oracle trunca, e o rollback quebra."""
    nomes = [c.name for c in Paciente._meta.constraints] + [i.name for i in Paciente._meta.indexes]
    assert nomes
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"


def test_cpf_hash_nao_tem_indice_duplicado() -> None:
    """`db_index=True` + UNIQUE na mesma coluna = ORA-01408 no Oracle."""
    campo = Paciente._meta.get_field("cpf_hash")
    assert campo.db_index is False
    assert campo.unique is False, "unicidade tem que vir da UniqueConstraint nomeada"


def test_nenhum_campo_textfield() -> None:
    """TextField vira NCLOB no Oracle — não é ordenável nem indexável."""
    from django.db import models as dj_models

    for campo in Paciente._meta.get_fields():
        assert not isinstance(campo, dj_models.TextField), f"{campo.name} é TextField"

"""Testes dos models do prontuário `[S1-8]` — ``Prontuario``, ``Evolucao`` e ``LogAcesso``.

Rodam em SQLite: cobrem o que é portável — unicidade do agregador, o
encadeamento de correções, a estabilidade do hash de autoria e o ``on_delete``
de cada FK.

O que **não** está aqui é a imutabilidade de ``EVOLUCAO``. Ela é um trigger
PL/SQL `[S1-10]` e só existe no Oracle; o teste correspondente vive em
``test_imutabilidade.py``, sob ``@pytest.mark.oracle``. Nada neste arquivo deve
dar a impressão de que a aplicação garante append-only — ela não garante, e
essa é a decisão de arquitetura.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.agenda.models import AgendaSlot, Consulta
from apps.crm.models import Medico, Paciente
from apps.prontuario.models import Evolucao, LogAcesso, Prontuario

pytestmark = pytest.mark.django_db

DIA = dt.date(2026, 8, 12)
NOVE_HORAS = dt.time(9, 0)
NOVE_E_MEIA = dt.time(9, 30)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def paciente() -> Paciente:
    p = Paciente(nome="Joana Silva", data_nascimento=dt.date(1980, 5, 3))
    p.definir_cpf("98765432100")
    p.save()
    return p


@pytest.fixture
def medica() -> Medico:
    return Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="SP")


@pytest.fixture
def prontuario(paciente: Paciente) -> Prontuario:
    return Prontuario.objects.create(paciente=paciente)


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="recepcao", password="x")  # noqa: S106


def _evolucao(prontuario: Prontuario, medico: Medico, **overrides: object) -> Evolucao:
    dados: dict[str, object] = {
        "prontuario": prontuario,
        "medico": medico,
        "texto": "Acuidade visual 20/20 em ambos os olhos.",
    }
    dados.update(overrides)
    return Evolucao.objects.create(**dados)


def _consulta(paciente: Paciente, medico: Medico) -> Consulta:
    slot = AgendaSlot.objects.create(
        medico=medico, data=DIA, hora_inicio=NOVE_HORAS, hora_fim=NOVE_E_MEIA
    )
    return Consulta.objects.create(paciente=paciente, slot=slot, medico=medico)


# ---------------------------------------------------------------------------
# Prontuario
# ---------------------------------------------------------------------------


def test_prontuario_nasce_datado_e_vazio(prontuario: Prontuario) -> None:
    assert prontuario.criado_em is not None
    assert prontuario.evolucoes.count() == 0


def test_prontuario_str_identifica_o_paciente(prontuario: Prontuario) -> None:
    assert str(prontuario) == "Prontuário de Joana Silva"


def test_paciente_tem_no_maximo_um_prontuario(prontuario: Prontuario, paciente: Paciente) -> None:
    """Dois prontuários para o mesmo paciente partiriam o histórico em dois."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Prontuario.objects.create(paciente=paciente)


def test_prontuario_e_alcancavel_pelo_paciente(prontuario: Prontuario, paciente: Paciente) -> None:
    assert paciente.prontuario == prontuario


def test_paciente_com_prontuario_nao_pode_ser_apagado(
    prontuario: Prontuario, paciente: Paciente
) -> None:
    with pytest.raises(ProtectedError):
        paciente.delete()


# ---------------------------------------------------------------------------
# Evolucao — autoria e encadeamento
# ---------------------------------------------------------------------------


def test_evolucao_guarda_autor_e_carimbo(prontuario: Prontuario, medica: Medico) -> None:
    evolucao = _evolucao(prontuario, medica)
    assert evolucao.medico == medica
    assert evolucao.criado_em is not None
    assert evolucao.consulta is None
    assert evolucao.evolucao_anterior is None


def test_evolucao_nao_tem_coluna_de_atualizacao() -> None:
    """``atualizado_em`` seria mentira estrutural numa tabela que o banco
    proíbe atualizar — se alguém reintroduzir a coluna, este teste avisa."""
    assert "atualizado_em" not in {campo.name for campo in Evolucao._meta.get_fields()}


def test_evolucao_anterior_encadeia_a_correcao(prontuario: Prontuario, medica: Medico) -> None:
    """O único caminho de retificação: linha nova apontando para a antiga."""
    original = _evolucao(prontuario, medica, texto="Pressão intraocular 14 mmHg.")
    correcao = _evolucao(
        prontuario,
        medica,
        texto="Correção: pressão intraocular 24 mmHg (erro de digitação).",
        evolucao_anterior=original,
    )

    assert correcao.evolucao_anterior == original
    assert list(original.correcoes.all()) == [correcao]
    # As duas sobrevivem — é o que torna a retificação auditável.
    assert prontuario.evolucoes.count() == 2


def test_evolucao_referencia_a_consulta_de_origem(
    prontuario: Prontuario, paciente: Paciente, medica: Medico
) -> None:
    consulta = _consulta(paciente, medica)
    evolucao = _evolucao(prontuario, medica, consulta=consulta)
    assert list(consulta.evolucoes.all()) == [evolucao]


def test_apagar_consulta_nao_leva_a_evolucao_junto(
    prontuario: Prontuario, paciente: Paciente, medica: Medico
) -> None:
    """SET_NULL: o registro clínico sobrevive ao agendamento que o originou."""
    consulta = _consulta(paciente, medica)
    evolucao = _evolucao(prontuario, medica, consulta=consulta)

    consulta.delete()

    evolucao.refresh_from_db()
    assert evolucao.consulta is None
    assert Evolucao.objects.filter(pk=evolucao.pk).exists()


def test_prontuario_com_evolucao_nao_pode_ser_apagado(
    prontuario: Prontuario, medica: Medico
) -> None:
    _evolucao(prontuario, medica)
    with pytest.raises(ProtectedError):
        prontuario.delete()


def test_medico_com_evolucao_nao_pode_ser_apagado(prontuario: Prontuario, medica: Medico) -> None:
    """Autoria é requisito de conformidade — não some do banco."""
    _evolucao(prontuario, medica)
    with pytest.raises(ProtectedError):
        medica.delete()


# ---------------------------------------------------------------------------
# Evolucao — hash de autoria
# ---------------------------------------------------------------------------


def test_hash_e_preenchido_no_insert(prontuario: Prontuario, medica: Medico) -> None:
    """Depois do INSERT a linha é intocável: hash esquecido é hash perdido."""
    evolucao = _evolucao(prontuario, medica)
    assert len(evolucao.conteudo_hash) == 64
    assert evolucao.conteudo_hash == evolucao.calcular_conteudo_hash()


def test_hash_e_estavel_entre_chamadas(prontuario: Prontuario, medica: Medico) -> None:
    evolucao = _evolucao(prontuario, medica)
    assert evolucao.calcular_conteudo_hash() == evolucao.calcular_conteudo_hash()


def test_hash_muda_quando_o_texto_muda(prontuario: Prontuario, medica: Medico) -> None:
    evolucao = _evolucao(prontuario, medica)
    antes = evolucao.conteudo_hash

    evolucao.texto = "Outro achado clínico."

    assert evolucao.calcular_conteudo_hash() != antes


def test_hash_muda_quando_o_autor_muda(prontuario: Prontuario, medica: Medico) -> None:
    """Dois médicos podem registrar a mesma frase; o hash tem que distingui-los."""
    outro = Medico.objects.create(nome="Bruno Costa", crm_numero="54321", crm_uf="RJ")
    de_uma = _evolucao(prontuario, medica, texto="Mesmo texto.")
    de_outro = _evolucao(prontuario, outro, texto="Mesmo texto.", criado_em=de_uma.criado_em)

    assert de_uma.conteudo_hash != de_outro.conteudo_hash


def test_hash_muda_quando_o_carimbo_muda(prontuario: Prontuario, medica: Medico) -> None:
    primeira = _evolucao(prontuario, medica, texto="Mesmo texto.")
    segunda = _evolucao(prontuario, medica, texto="Mesmo texto.")

    assert primeira.criado_em != segunda.criado_em
    assert primeira.conteudo_hash != segunda.conteudo_hash


def test_hash_informado_e_preservado(prontuario: Prontuario, medica: Medico) -> None:
    """Prontuário legado importado traz o hash da origem — não recalculamos."""
    de_fora = "f" * 64
    evolucao = _evolucao(prontuario, medica, conteudo_hash=de_fora)
    assert evolucao.conteudo_hash == de_fora


# ---------------------------------------------------------------------------
# LogAcesso
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("acao", [a.value for a in LogAcesso.Acao])
def test_log_acesso_grava_as_tres_acoes(paciente: Paciente, usuario, acao: str) -> None:
    log = LogAcesso.objects.create(usuario=usuario, paciente=paciente, acao=acao)
    assert log.acao == acao
    assert log.criado_em is not None


def test_log_acesso_aceita_origem_sem_ip(paciente: Paciente, usuario) -> None:
    """Comando e task Celery não têm IP de cliente; inventar seria pior."""
    log = LogAcesso.objects.create(
        usuario=usuario, paciente=paciente, acao=LogAcesso.Acao.VISUALIZOU
    )
    assert log.ip is None
    assert log.user_agent == ""


def test_log_acesso_registra_ip_e_user_agent(paciente: Paciente, usuario) -> None:
    log = LogAcesso.objects.create(
        usuario=usuario,
        paciente=paciente,
        acao=LogAcesso.Acao.EXPORTOU,
        ip="192.0.2.10",
        user_agent="Mozilla/5.0",
    )
    log.refresh_from_db()
    assert log.ip == "192.0.2.10"
    assert log.user_agent == "Mozilla/5.0"


def test_log_acesso_str_descreve_o_evento(paciente: Paciente, usuario) -> None:
    log = LogAcesso.objects.create(
        usuario=usuario, paciente=paciente, acao=LogAcesso.Acao.VISUALIZOU
    )
    assert str(log) == "recepcao visualizou Joana Silva"


def test_usuario_com_log_nao_pode_ser_apagado(paciente: Paciente, usuario) -> None:
    """Apagar o usuário levaria junto a prova de quem viu o dado."""
    LogAcesso.objects.create(usuario=usuario, paciente=paciente, acao=LogAcesso.Acao.VISUALIZOU)
    with pytest.raises(ProtectedError):
        usuario.delete()


def test_paciente_com_log_nao_pode_ser_apagado(paciente: Paciente, usuario) -> None:
    LogAcesso.objects.create(usuario=usuario, paciente=paciente, acao=LogAcesso.Acao.VISUALIZOU)
    with pytest.raises(ProtectedError):
        paciente.delete()

"""Testes do comando ``seed_initial`` — os números do DoD e a idempotência (S1-16).

O teste que realmente importa aqui é ``test_rodar_duas_vezes_nao_muda_nada``: o
seed é chamado por ``infra/scripts/setup.sh`` em **todo** ``make setup``, então
uma segunda execução que duplique linha (ou que estoure) quebra o ambiente de
quem já tinha o banco populado. Ele é escrito como comparação de dicionário de
contagens, e não como uma lista de ``assert`` por model, para que um model novo
semeado no futuro entre na verificação só mexendo em ``_contagens``.

Rodam em SQLite, como o resto da suíte. O que **não** dá para cobrir aqui é o
trigger ``TRG_EVOLUCAO_IMUTAVEL``: ele é PL/SQL e só existe no Oracle (ver
``apps/prontuario/test_imutabilidade.py``, marcado com ``@pytest.mark.oracle``).
O que este arquivo garante é o outro lado da mesma moeda — que a segunda
execução do seed **não tenta** escrever de novo na evolução já gravada, que é o
que faria o trigger disparar.
"""

from __future__ import annotations

import datetime as dt
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from apps.agenda.models import AgendaRegra, AgendaSlot, Consulta
from apps.chatbot.models import FaqVector
from apps.core.management.commands.seed_initial import SENHA_DEV_PADRAO, SUPERUSUARIO_PADRAO
from apps.crm.models import Especialidade, Lead, Medico, Paciente
from apps.prontuario.models import Evolucao, LogAcesso, Prontuario

pytestmark = pytest.mark.django_db


def _semear() -> None:
    """Roda o comando engolindo a saída — o teste inspeciona o banco, não o texto."""
    call_command("seed_initial", stdout=StringIO(), stderr=StringIO())


def _contagens() -> dict[str, int]:
    return {
        "especialidades": Especialidade.objects.count(),
        "medicos": Medico.objects.count(),
        "pacientes": Paciente.objects.count(),
        "regras": AgendaRegra.objects.count(),
        "slots": AgendaSlot.objects.count(),
        "consultas": Consulta.objects.count(),
        "leads": Lead.objects.count(),
        "prontuarios": Prontuario.objects.count(),
        "evolucoes": Evolucao.objects.count(),
        "faqs": FaqVector.objects.count(),
        "usuarios": get_user_model().objects.count(),
    }


def _cpf_valido(cpf: str) -> bool:
    """Validação independente dos dígitos verificadores (implementação da Receita).

    Escrita à mão, e não importada do comando, de propósito: um teste que reusa a
    função sob teste concorda com ela até quando as duas estão erradas.
    """
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * (tamanho + 1 - i) for i, d in enumerate(cpf[:tamanho]))
        resto = soma % 11
        esperado = 0 if resto < 2 else 11 - resto
        if int(cpf[tamanho]) != esperado:
            return False
    return True


@pytest.fixture
def semeado() -> None:
    _semear()


# ---------------------------------------------------------------------------
# Idempotência — o critério de aceite principal da S1-16
# ---------------------------------------------------------------------------


def test_rodar_duas_vezes_nao_muda_nada() -> None:
    _semear()
    primeira = _contagens()

    _semear()  # não pode duplicar nada nem levantar exceção

    assert _contagens() == primeira


def test_segunda_execucao_nao_reescreve_a_evolucao_ja_gravada() -> None:
    """``EVOLUCAO`` é append-only no Oracle: reescrever levantaria ``ORA-20001``.

    No SQLite não há trigger, então o que se verifica é o comportamento que o
    evita: mesmas linhas, mesmos ``id`` e mesmos hashes de conteúdo depois da
    segunda passada.
    """
    _semear()
    antes = list(Evolucao.objects.order_by("id").values_list("id", "conteudo_hash", "criado_em"))

    _semear()

    assert antes
    assert (
        list(Evolucao.objects.order_by("id").values_list("id", "conteudo_hash", "criado_em"))
        == antes
    )


# ---------------------------------------------------------------------------
# Superusuário do Admin
# ---------------------------------------------------------------------------
# O Admin é a UI do CRM no MVP1 (ADR-0005), então "semeou mas ninguém consegue
# logar" é o mesmo que não ter semeado. O que estes testes protegem é a guarda:
# a senha padrão é conhecida (está na documentação), e um superusuário com ela
# não pode nascer fora de `DEBUG`.


def test_sem_senha_no_ambiente_e_sem_debug_nao_cria_superusuario(semeado: None) -> None:
    """``config/settings/test.py`` roda com ``DEBUG=False`` — é o caso de produção."""
    assert not get_user_model().objects.exists()


@override_settings(DEBUG=True)
def test_com_debug_cria_o_superusuario_de_dev() -> None:
    # Sem a fixture `semeado` de propósito: ela roda **antes** de o
    # `override_settings` valer, então semearia com `DEBUG=False` e o
    # superusuário nem seria criado.
    _semear()

    usuario = get_user_model().objects.get(username=SUPERUSUARIO_PADRAO)

    assert usuario.is_superuser
    assert usuario.is_staff
    assert usuario.perfil == get_user_model().Perfil.ADMIN
    # A senha precisa chegar hasheada: `get_or_create` com `password` no
    # `defaults` gravaria o texto em claro e o login falharia.
    assert usuario.check_password(SENHA_DEV_PADRAO)


def test_senha_do_ambiente_dispensa_o_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "senha-vinda-do-ambiente")

    _semear()

    usuario = get_user_model().objects.get(username=SUPERUSUARIO_PADRAO)
    assert usuario.check_password("senha-vinda-do-ambiente")


@override_settings(DEBUG=True)
def test_segunda_execucao_nao_redefine_a_senha() -> None:
    """Quem trocou a própria senha não a perde no próximo ``make setup``."""
    _semear()
    usuario = get_user_model().objects.get(username=SUPERUSUARIO_PADRAO)
    usuario.set_password("trocada-pelo-dev")
    usuario.save(update_fields=["password"])

    _semear()

    usuario.refresh_from_db()
    assert usuario.check_password("trocada-pelo-dev")


# ---------------------------------------------------------------------------
# Números do DoD
# ---------------------------------------------------------------------------


def test_numeros_do_dod(semeado: None) -> None:
    contagens = _contagens()
    assert contagens["medicos"] == 5
    assert contagens["pacientes"] == 50
    assert contagens["slots"] >= 200
    assert contagens["faqs"] == 20


def test_cada_medico_tem_especialidade_e_regra_de_agenda(semeado: None) -> None:
    for medico in Medico.objects.all():
        assert medico.especialidades.exists()
        assert medico.regras.exists()


def test_slots_futuros_sao_pelo_menos_duzentos(semeado: None) -> None:
    hoje = dt.date.today()
    assert AgendaSlot.objects.filter(data__gt=hoje).count() >= 200


# ---------------------------------------------------------------------------
# Coerência dos dados semeados
# ---------------------------------------------------------------------------


def test_todo_cpf_semeado_tem_digitos_verificadores_validos(semeado: None) -> None:
    cpfs = [paciente.cpf for paciente in Paciente.objects.all()]
    assert len(set(cpfs)) == 50
    invalidos = [cpf for cpf in cpfs if not _cpf_valido(cpf)]
    assert invalidos == []


def test_slot_com_consulta_esta_reservado(semeado: None) -> None:
    livres_com_consulta = Consulta.objects.exclude(slot__status=AgendaSlot.Status.RESERVADO)
    assert not livres_com_consulta.exists()


def test_consultas_cobrem_todos_os_status_e_origens(semeado: None) -> None:
    status = set(Consulta.objects.values_list("status", flat=True))
    origens = set(Consulta.objects.values_list("origem", flat=True))
    assert status == {opcao.value for opcao in Consulta.Status}
    assert origens == {opcao.value for opcao in Consulta.Origem}


def test_consulta_realizada_esta_no_passado_e_agendada_no_futuro(semeado: None) -> None:
    hoje = dt.date.today()
    resolvidos = (Consulta.Status.REALIZADA, Consulta.Status.FALTOU, Consulta.Status.CANCELADA)
    assert not Consulta.objects.filter(status__in=resolvidos, slot__data__gt=hoje).exists()
    abertos = (Consulta.Status.AGENDADA, Consulta.Status.CONFIRMADA)
    assert not Consulta.objects.filter(status__in=abertos, slot__data__lt=hoje).exists()


def test_funil_de_leads_cobre_as_cinco_etapas_e_tem_conversao(semeado: None) -> None:
    etapas = set(Lead.objects.values_list("etapa", flat=True))
    assert etapas == {opcao.value for opcao in Lead.Etapa}
    convertidos = Lead.objects.filter(consulta__isnull=False)
    assert convertidos.exists()
    # Lead com consulta não pode estar no topo do funil.
    assert not convertidos.filter(etapa__in=(Lead.Etapa.NOVO, Lead.Etapa.QUALIFICADO)).exists()


def test_evolucao_existe_para_paciente_com_consulta_realizada(semeado: None) -> None:
    realizadas = Consulta.objects.filter(status=Consulta.Status.REALIZADA)
    assert realizadas.exists()
    for consulta in realizadas:
        assert Prontuario.objects.filter(paciente=consulta.paciente).exists()
        assert Evolucao.objects.filter(consulta=consulta).exists()


def test_parte_dos_slots_fica_vinculada_a_uma_regra(semeado: None) -> None:
    """Antes da S1-16 a coluna ``REGRA_ID`` era integralmente nula."""
    assert AgendaSlot.objects.filter(regra__isnull=False).exists()
    vinculados = AgendaSlot.objects.filter(regra__isnull=False).select_related("regra")
    for slot in vinculados[:50]:
        assert slot.regra.medico_id == slot.medico_id
        assert slot.regra.dia_semana == slot.data.weekday()
        assert slot.regra.hora_inicio <= slot.hora_inicio < slot.regra.hora_fim


def test_seed_nao_escreve_na_trilha_de_auditoria(semeado: None) -> None:
    """``LOG_ACESSO`` é populado pelo middleware da Sprint 6 — auditoria falsa polui a trilha."""
    assert LogAcesso.objects.count() == 0

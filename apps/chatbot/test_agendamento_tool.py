"""Testes da ferramenta de escrita do chatbot `[S5-12]` `[S5-24]`.

Rodam em SQLite, como o resto da suíte padrão. O que se verifica é o **contrato
com o modelo**: o que a tool aceita, o que ela recusa, o que sobra no banco
depois de cada recusa, e o que ela devolve para ser verbalizado.

Duas classes de teste merecem leitura antes de qualquer alteração aqui:

``TestRecusaHorarioInventado``
    A porta que impede o chatbot de agendar um horário que ninguém ofereceu.
    Se algum dia esses testes começarem a aceitar texto livre no ``slot_id``,
    o grounding do agendamento acabou.

``TestNaoDeixaLixo``
    Toda recusa tem que sair sem paciente órfão. Um cadastro criado por um
    agendamento que falhou não é só sujeira: ele **bloqueia o CPF** na segunda
    tentativa do mesmo paciente, via ``UK_PACIENTE_CPF_HASH``.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from django.utils import timezone

from apps.agenda.models import AgendaSlot, Consulta
from apps.chatbot.models import InteracaoChat
from apps.chatbot.services.chat import ChatService
from apps.chatbot.services.llm.base import RespostaLLM, ToolCall
from apps.chatbot.services.llm.fake import FakeLLMClient
from apps.chatbot.tools import (
    CriarLeadEConsultaTool,
    ToolError,
    ToolRegistry,
    construir_registry,
)
from apps.crm.models import Especialidade, Lead, Medico, MedicoEspecialidade, Paciente

pytestmark = pytest.mark.django_db

# Dois CPFs válidos nos dígitos verificadores — a tool recusa qualquer outro
# antes de tocar no banco.
CPF_JOANA = "12345678909"
CPF_CARLOS = "98765432100"

AMANHA = timezone.localdate() + dt.timedelta(days=1)
CONVERSA = uuid.UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def slot() -> AgendaSlot:
    """Um slot livre amanhã às 9h, com médico e especialidade por trás."""
    esp = Especialidade.objects.create(nome="Retina", slug="retina")
    medico = Medico.objects.create(nome="Ana Ribeiro", crm_numero="12345", crm_uf="RS")
    MedicoEspecialidade.objects.create(medico=medico, especialidade=esp, principal=True)
    return AgendaSlot.objects.create(
        medico=medico,
        data=AMANHA,
        hora_inicio=dt.time(9, 0),
        hora_fim=dt.time(9, 30),
    )


@pytest.fixture
def tool() -> CriarLeadEConsultaTool:
    return CriarLeadEConsultaTool(conversa_id=CONVERSA)


def _dados(slot: AgendaSlot, **overrides: object) -> dict[str, object]:
    dados: dict[str, object] = {
        "nome": "Joana Prado",
        "cpf": CPF_JOANA,
        "data_nascimento": "17/05/1980",
        "telefone": "(51) 99999-0000",
        "slot_id": slot.pk,
    }
    dados.update(overrides)
    return dados


# ---------------------------------------------------------------------------
# Caminho feliz [S5-12] [S5-24]
# ---------------------------------------------------------------------------
class TestAgendamentoCompleto:
    def test_cria_paciente_consulta_e_lead(self, tool, slot):
        resultado = tool.execute(**_dados(slot, email="joana@exemplo.com"))

        paciente = Paciente.objects.get()
        assert paciente.nome == "Joana Prado"
        assert paciente.cpf == CPF_JOANA  # descriptografa: passou por definir_cpf
        assert paciente.data_nascimento == dt.date(1980, 5, 17)

        consulta = Consulta.objects.get()
        assert consulta.paciente == paciente
        assert consulta.slot == slot
        assert consulta.medico == slot.medico
        # A origem é o denominador da métrica de conversão do chatbot [S5-28]:
        # se ela vier errada, o agendamento funciona e a medição mente.
        assert consulta.origem == Consulta.Origem.CHAT

        slot.refresh_from_db()
        assert slot.status == AgendaSlot.Status.RESERVADO

        lead = Lead.objects.get()
        assert lead.etapa == Lead.Etapa.AGENDADO
        assert lead.consulta == consulta
        assert lead.conversa_id == CONVERSA

        assert resultado["agendada"] is True

    def test_retorno_traz_o_que_o_modelo_precisa_verbalizar(self, tool, slot):
        """Confirmação com médico, data, hora e nome — em português e raso."""
        resultado = tool.execute(**_dados(slot))

        assert resultado["medico"] == "Ana Ribeiro"
        assert resultado["data"] == AMANHA.strftime("%d/%m/%Y")
        assert resultado["hora"] == "09:00"
        assert resultado["paciente"] == "Joana Prado"
        assert all(not isinstance(v, (dict, list)) for v in resultado.values())

    def test_aceita_data_no_formato_iso(self, tool, slot):
        """O modelo às vezes devolve AAAA-MM-DD sozinho; perder o agendamento
        por causa disso seria caro demais."""
        tool.execute(**_dados(slot, data_nascimento="1980-05-17"))

        assert Paciente.objects.get().data_nascimento == dt.date(1980, 5, 17)

    def test_cpf_com_mascara_e_o_mesmo_cpf(self, tool, slot):
        tool.execute(**_dados(slot, cpf="123.456.789-09"))

        assert Paciente.objects.buscar_por_cpf(CPF_JOANA).count() == 1


# ---------------------------------------------------------------------------
# Paciente já cadastrado
# ---------------------------------------------------------------------------
class TestPacienteExistente:
    def test_reaproveita_cadastro_do_mesmo_cpf(self, tool, slot):
        """``UK_PACIENTE_CPF_HASH`` recusaria o segundo cadastro — e mais do que
        isso, quem já se consultou não pode virar um prontuário paralelo."""
        antigo = Paciente(nome="Joana Prado da Silva", data_nascimento=dt.date(1980, 5, 17))
        antigo.definir_cpf(CPF_JOANA)
        antigo.save()

        tool.execute(**_dados(slot))

        assert Paciente.objects.count() == 1
        assert Consulta.objects.get().paciente_id == antigo.pk

    def test_nao_sobrescreve_o_cadastro_com_o_que_o_modelo_transcreveu(self, tool, slot):
        """Dado de conversa é não verificado; o do balcão foi conferido."""
        antigo = Paciente(
            nome="Joana Prado da Silva",
            data_nascimento=dt.date(1980, 5, 17),
            telefone="(51) 3000-0000",
        )
        antigo.definir_cpf(CPF_JOANA)
        antigo.save()

        tool.execute(**_dados(slot, nome="joana", telefone="(51) 98888-1111"))

        antigo.refresh_from_db()
        assert antigo.nome == "Joana Prado da Silva"
        assert antigo.telefone == "(51) 3000-0000"


# ---------------------------------------------------------------------------
# Funil do CRM [S5-24]
# ---------------------------------------------------------------------------
class TestLeadDaConversa:
    def test_lead_pre_existente_e_atualizado_e_nao_duplicado(self, tool, slot):
        lead = Lead.objects.create(nome="Joana", conversa_id=CONVERSA, etapa=Lead.Etapa.NOVO)

        tool.execute(**_dados(slot))

        assert Lead.objects.count() == 1
        lead.refresh_from_db()
        assert lead.etapa == Lead.Etapa.AGENDADO
        assert lead.consulta == Consulta.objects.get()

    def test_completa_contato_em_branco_sem_apagar_o_que_ja_havia(self, tool, slot):
        lead = Lead.objects.create(
            nome="Joana",
            conversa_id=CONVERSA,
            telefone="(51) 3000-0000",
            etapa=Lead.Etapa.QUALIFICADO,
        )

        tool.execute(**_dados(slot, telefone="(51) 98888-1111", email="joana@exemplo.com"))

        lead.refresh_from_db()
        assert lead.telefone == "(51) 3000-0000"
        assert lead.email == "joana@exemplo.com"

    def test_lead_de_outra_conversa_nao_e_tocado(self, tool, slot):
        alheio = Lead.objects.create(
            nome="Outra pessoa", conversa_id=uuid.uuid4(), etapa=Lead.Etapa.NOVO
        )

        tool.execute(**_dados(slot))

        alheio.refresh_from_db()
        assert alheio.etapa == Lead.Etapa.NOVO
        assert alheio.consulta is None

    def test_sem_conversa_nao_sequestra_lead_da_recepcao(self, slot):
        """``conversa_id=None`` casaria com todo lead cadastrado à mão: sem o
        guarda, o primeiro deles seria marcado como agendado por engano."""
        recepcao = Lead.objects.create(nome="Cadastro do balcão", etapa=Lead.Etapa.NOVO)

        CriarLeadEConsultaTool().execute(**_dados(slot))

        recepcao.refresh_from_db()
        assert recepcao.etapa == Lead.Etapa.NOVO
        assert Lead.objects.filter(etapa=Lead.Etapa.AGENDADO).count() == 1


# ---------------------------------------------------------------------------
# A porta fechada para horário inventado
# ---------------------------------------------------------------------------
class TestRecusaHorarioInventado:
    @pytest.mark.parametrize(
        "slot_id",
        ["quinta às 15h", "amanhã", "", None, True, "9:00", {"data": "amanhã"}],
    )
    def test_slot_id_so_aceita_numero_de_buscar_slots(self, tool, slot, slot_id):
        with pytest.raises(ToolError):
            tool.execute(**_dados(slot, slot_id=slot_id))

        assert Consulta.objects.count() == 0

    def test_schema_nao_tem_campo_de_data_nem_de_hora(self):
        """Se um dia existir, o modelo passa a poder marcar o que quiser."""
        propriedades = CriarLeadEConsultaTool.input_schema["properties"]

        assert set(propriedades) == {
            "nome",
            "cpf",
            "data_nascimento",
            "telefone",
            "slot_id",
            "email",
        }
        assert propriedades["slot_id"]["type"] == "integer"

    def test_email_e_o_unico_opcional(self):
        obrigatorios = CriarLeadEConsultaTool.input_schema["required"]

        assert set(obrigatorios) == {"nome", "cpf", "data_nascimento", "telefone", "slot_id"}

    def test_conversa_id_nao_e_argumento_do_modelo(self):
        """Se fosse, uma alucinação (ou uma injeção) mexeria no funil alheio."""
        assert "conversa_id" not in CriarLeadEConsultaTool.input_schema["properties"]

    def test_slot_inexistente_nao_vaza_a_existencia_da_linha(self, tool, slot):
        with pytest.raises(ToolError) as erro:
            tool.execute(**_dados(slot, slot_id=987654))

        assert "987654" not in str(erro.value)


# ---------------------------------------------------------------------------
# Recusas, vistas como o modelo as vê (via registry, que serializa)
# ---------------------------------------------------------------------------
class TestNaoDeixaLixo:
    def _executar(self, tool, **argumentos: object) -> dict:
        """Passa pelo registry de propósito: é assim que o turno real chama."""
        return json.loads(ToolRegistry([tool]).executar("criar_lead_e_consulta", dict(argumentos)))

    def test_cpf_invalido_vira_erro_e_nao_cria_nada(self, tool, slot):
        payload = self._executar(tool, **_dados(slot, cpf="12345678900"))

        assert "CPF" in payload["erro"]
        assert Paciente.objects.count() == 0
        assert Consulta.objects.count() == 0
        assert Lead.objects.count() == 0

    def test_cpf_de_digitos_repetidos_e_recusado(self, tool, slot):
        """Passa em ``normalize_cpf`` e é a forma clássica de burlar validação."""
        payload = self._executar(tool, **_dados(slot, cpf="11111111111"))

        assert "erro" in payload
        assert Paciente.objects.count() == 0

    def test_data_de_nascimento_ilegivel_da_erro_claro(self, tool, slot):
        payload = self._executar(tool, **_dados(slot, data_nascimento="ontem"))

        assert "data de nascimento" in payload["erro"]
        assert "17/05/1980" in payload["erro"]  # o formato esperado, por exemplo
        assert Paciente.objects.count() == 0

    def test_slot_ocupado_explica_e_oferece_outro(self, tool, slot):
        """O caso mais provável em produção: o horário foi tomado entre a busca
        e a confirmação. Não pode sobrar paciente órfão — ele bloquearia o CPF
        na segunda tentativa do mesmo paciente."""
        slot.status = AgendaSlot.Status.RESERVADO
        slot.save(update_fields=["status"])

        payload = self._executar(tool, **_dados(slot))

        assert "disponível" in payload["erro"]
        assert "outros horários" in payload["erro"]
        assert Paciente.objects.count() == 0
        assert Consulta.objects.count() == 0
        assert Lead.objects.count() == 0

    def test_corrida_perdida_nao_deixa_paciente_orfao(self, tool, slot):
        """O slot ainda consta ``LIVRE`` e a consulta já existe — o estado que a
        transação perdedora enxerga."""
        outro = Paciente(nome="Carlos Lima", data_nascimento=dt.date(1975, 1, 2))
        outro.definir_cpf(CPF_CARLOS)
        outro.save()
        Consulta.objects.create(paciente=outro, slot=slot, medico=slot.medico)

        payload = self._executar(tool, **_dados(slot))

        assert "erro" in payload
        assert Paciente.objects.count() == 1  # só o Carlos, que já existia
        assert Consulta.objects.count() == 1

    def test_dado_faltando_pede_o_dado_em_vez_de_agendar(self, tool, slot):
        payload = self._executar(tool, **_dados(slot, nome="   "))

        assert "nome" in payload["erro"]
        assert Consulta.objects.count() == 0

    def test_erro_nao_vaza_detalhe_tecnico(self, tool, slot):
        slot.status = AgendaSlot.Status.BLOQUEADO
        slot.save(update_fields=["status"])

        mensagem = self._executar(tool, **_dados(slot))["erro"]

        for vazamento in ("Traceback", "ORA-", "UK_", "IntegrityError", "SELECT", str(slot.pk)):
            assert vazamento not in mensagem


# ---------------------------------------------------------------------------
# Montagem do registry e turno ponta a ponta
# ---------------------------------------------------------------------------
class TestRegistryDoTurno:
    def test_registry_expoe_a_tool_de_escrita(self, slot):
        assert "criar_lead_e_consulta" in construir_registry().nomes()

    def test_conversa_id_chega_ate_a_tool(self, slot):
        """A injeção que substitui um argumento que o modelo não pode fornecer."""
        registry = construir_registry(conversa_id=CONVERSA)
        Lead.objects.create(nome="Joana", conversa_id=CONVERSA, etapa=Lead.Etapa.NOVO)

        registry.executar("criar_lead_e_consulta", _dados(slot))

        assert Lead.objects.count() == 1
        assert Lead.objects.get().etapa == Lead.Etapa.AGENDADO

    def test_turno_completo_agenda_de_verdade(self, slot):
        """Do ``tool_call`` do modelo até a linha no banco, sem rede."""
        cliente = FakeLLMClient(
            respostas=[
                RespostaLLM(
                    tool_calls=[ToolCall("c1", "criar_lead_e_consulta", _dados(slot))],
                )
            ],
            fragmentos=["Pronto! ", "Consulta confirmada."],
        )
        servico = ChatService(
            cliente=cliente,
            registry=construir_registry(conversa_id=CONVERSA),
        )

        eventos = "".join(
            servico.responder(pergunta="pode marcar às 9h", conversa_id=CONVERSA, sequencia=1)
        )

        assert "Consulta confirmada." in eventos
        assert Consulta.objects.get().origem == Consulta.Origem.CHAT
        assert Lead.objects.get().etapa == Lead.Etapa.AGENDADO
        # O resultado da tool volta para o modelo na segunda chamada, e é dele
        # que sai a frase final — é o rastro de grounding do turno.
        assert "criar_lead_e_consulta" in InteracaoChat.objects.get().tools_usadas

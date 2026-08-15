"""Testes do ChatService, do framing SSE e dos guardrails.

Rodam no CI: o ``LLMClient`` é substituído pelo fake, então não há rede nem
GPU envolvida. É a suíte mais valiosa do app — cobre o loop de tool use
inteiro e o protocolo de eventos, que é onde moram os defeitos sutis.
"""

from __future__ import annotations

import json
import uuid

import pytest

from apps.chatbot import guardrails, sse
from apps.chatbot.models import InteracaoChat
from apps.chatbot.services.chat import (
    ChatService,
    _FiltroSlotId,
    _sem_slot_id,
    detectar_alucinacao,
)
from apps.chatbot.services.llm.base import (
    FragmentoStream,
    LLMIndisponivelError,
    RespostaLLM,
    ToolCall,
)
from apps.chatbot.services.llm.fake import FakeLLMClient
from apps.chatbot.tools import BaseTool, ToolRegistry


class _ToolFalsa(BaseTool):
    name = "buscar_slots"
    description = "falsa"
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, retorno=None):
        self._retorno = retorno if retorno is not None else {"slots": []}

    def execute(self, **kwargs):
        return self._retorno


def _eventos(stream) -> list[tuple[str, str]]:
    """Converte o stream bruto em pares (evento, dado), ignorando keepalive."""
    pares: list[tuple[str, str]] = []
    for bloco in "".join(stream).split("\n\n"):
        if not bloco.strip() or bloco.startswith(":"):
            continue
        nome = ""
        dados: list[str] = []
        for linha in bloco.split("\n"):
            if linha.startswith("event: "):
                nome = linha[7:]
            elif linha.startswith("data: "):
                dados.append(linha[6:])
        pares.append((nome, "\n".join(dados)))
    return pares


def _texto(pares) -> str:
    return "".join(d for n, d in pares if n == "token")


# ---------------------------------------------------------------------------
# Framing SSE
# ---------------------------------------------------------------------------
class TestFramingSSE:
    def test_evento_tem_nome_e_dado(self):
        assert sse.evento("status", "oi") == "event: status\ndata: oi\n\n"

    def test_quebra_de_linha_vira_varias_linhas_data(self):
        """O protocolo reconcatena com \\n. O spike trocava por espaço e
        destruía a formatação da resposta."""
        assert sse.evento("token", "a\nb") == "event: token\ndata: a\ndata: b\n\n"

    def test_carriage_return_nao_deixa_linha_fantasma(self):
        assert sse.evento("token", "a\r\nb") == "event: token\ndata: a\ndata: b\n\n"

    def test_html_e_escapado(self):
        """htmx/EventSource podem injetar como HTML; a saída do LLM contém
        entrada do usuário, então é vetor de XSS por prompt injection."""
        assert "&lt;img" in sse.token("<img onerror=alert(1)>")
        assert "<img" not in sse.token("<img onerror=alert(1)>")

    def test_fragmento_partido_nao_recompoe_tag(self):
        saida = sse.token("<scr") + sse.token("ipt>")
        assert "<script>" not in saida


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
class TestGuardrails:
    @pytest.mark.parametrize(
        "pergunta",
        [
            "Me dá uma receita de colírio",
            "qual o remédio pra olho seco?",
            "quantas gotas eu uso?",
            "pode me indicar um antibiótico?",
        ],
    )
    def test_pedido_de_conduta_medica_e_interceptado(self, pergunta):
        resultado = guardrails.interceptar(pergunta)
        assert resultado is not None
        assert resultado.motivo == "conduta_medica"

    @pytest.mark.parametrize(
        "pergunta",
        [
            "perdi a visão do olho direito",
            "meu olho está com dor muito forte",
            "estou com dor forte no olho",
            "bati o olho e está sangrando",
            "estou vendo flashes de luz",
            "caiu produto químico no meu olho",
        ],
    )
    def test_sinal_de_urgencia_e_interceptado(self, pergunta):
        """Falso negativo aqui é muito mais caro que falso positivo."""
        resultado = guardrails.interceptar(pergunta)
        assert resultado is not None
        assert resultado.motivo == "urgencia"

    @pytest.mark.parametrize(
        "pergunta",
        [
            "Tem horário com oftalmologista?",
            "A clínica atende convênio?",
            "meu olho está um pouco vermelho",
            "preciso tirar a lente de contato antes?",
        ],
    )
    def test_pergunta_normal_passa_direto(self, pergunta):
        assert guardrails.interceptar(pergunta) is None

    def test_urgencia_tem_prioridade_sobre_conduta(self):
        """Quem descreve emergência precisa da orientação de urgência, não de
        uma recusa educada sobre medicamento."""
        resultado = guardrails.interceptar("perdi a visão, qual colírio devo usar?")
        assert resultado is not None
        assert resultado.motivo == "urgencia"


# ---------------------------------------------------------------------------
# Detecção de alucinação
# ---------------------------------------------------------------------------
class TestDetectarAlucinacao:
    def test_horario_que_veio_da_ferramenta_nao_e_acusado(self):
        fonte = ['{"slots": [{"hora": "09:00", "medico": "Dra. Ana Lima"}]}']
        assert detectar_alucinacao("Temos às 09:00 com a Dra. Ana Lima.", fonte) == []

    def test_horario_inventado_e_acusado(self):
        fonte = ['{"slots": [{"hora": "09:00"}]}']
        assert "14:00" in detectar_alucinacao("Temos às 09:00 e também às 14:00.", fonte)

    def test_medico_inventado_e_acusado(self):
        fonte = ['{"slots": [{"medico": "Dra. Ana Lima"}]}']
        assert detectar_alucinacao("Fale com o Dr. Fulano Silva.", fonte)

    def test_formato_de_hora_diferente_nao_gera_falso_positivo(self):
        """A ferramenta devolve 09:00 e o modelo costuma escrever 09h00."""
        assert detectar_alucinacao("Temos às 09h00.", ['{"hora": "09:00"}']) == []

    def test_texto_vazio_nao_acusa(self):
        assert detectar_alucinacao("", ['{"slots": []}']) == []


# ---------------------------------------------------------------------------
# Remoção do slot_id da resposta
# ---------------------------------------------------------------------------
class TestSemSlotId:
    """O `slot_id` é chave de banco: serve à tool, nunca ao paciente."""

    @pytest.mark.parametrize(
        "texto",
        [
            "09:00 com Dr. Bruno Carvalho (slot_id 1)",
            "09:00 com Dr. Bruno Carvalho (slot_id: 1)",
            "09:00 com Dr. Bruno Carvalho [slot_id 1]",
            "09:00 com Dr. Bruno Carvalho - slot_id 1",
            "09:00 com Dr. Bruno Carvalho, slot_id=1",
            "09:00 com Dr. Bruno Carvalho (slot id nº 1)",
            "09:00 com Dr. Bruno Carvalho (SLOT_ID 1)",
        ],
    )
    def test_mencao_ao_slot_id_some_da_frase(self, texto):
        assert _sem_slot_id(texto) == "09:00 com Dr. Bruno Carvalho"

    def test_frase_sem_slot_id_fica_intacta(self):
        frase = "Temos 09:00 e 09:30 com o Dr. Bruno Carvalho. Qual você prefere?"
        assert _sem_slot_id(frase) == frase

    def test_lista_inteira_e_limpa(self):
        bruto = "- 09:00 com Dr. Bruno (slot_id 1)\n- 09:30 com Dr. Bruno (slot_id 4)"
        assert _sem_slot_id(bruto) == "- 09:00 com Dr. Bruno\n- 09:30 com Dr. Bruno"


class TestFiltroSlotIdEmStream:
    """No stream a menção chega partida — filtrar fragmento a fragmento falha."""

    def _rodar(self, fragmentos):
        filtro = _FiltroSlotId()
        return "".join([*(filtro.filtrar(f) for f in fragmentos), filtro.esvaziar()])

    def test_mencao_partida_entre_fragmentos_nao_vaza(self):
        fragmentos = ["09:00 ", "com ", "Dr. ", "Bruno ", "(slot", "_id ", "1)", " — ", "confirma?"]
        assert self._rodar(fragmentos) == "09:00 com Dr. Bruno — confirma?"

    def test_texto_normal_atravessa_inteiro(self):
        fragmentos = ["Temos ", "vagas ", "na ", "segunda ", "às ", "09:00."]
        assert self._rodar(fragmentos) == "Temos vagas na segunda às 09:00."

    def test_palavra_com_s_no_fim_do_stream_nao_e_engolida(self):
        """O 's' final fica retido por precaução; `esvaziar` tem que devolvê-lo."""
        assert self._rodar(["Temos ", "vagas"]) == "Temos vagas"

    def test_slot_id_no_ultimo_fragmento_nao_escapa_pelo_esvaziar(self):
        assert self._rodar(["Escolha o ", "horário (slot_id 7)"]) == "Escolha o horário"


# ---------------------------------------------------------------------------
# ChatService
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestChatService:
    def _rodar(self, cliente, registry=None, pergunta="Tem horário?"):
        servico = ChatService(cliente=cliente, registry=registry or ToolRegistry([_ToolFalsa()]))
        return _eventos(servico.responder(pergunta=pergunta, conversa_id=uuid.uuid4()))

    def test_sem_tool_reaproveita_o_texto_da_primeira_chamada(self):
        """Uma segunda chamada dobraria a latência sem entregar nada novo."""
        cliente = FakeLLMClient(respostas=[RespostaLLM(texto="Olá! Como ajudo?")])
        pares = self._rodar(cliente)

        assert _texto(pares) == "Olá! Como ajudo?"
        assert cliente.chamadas_stream == [], "não deveria ter feito a 2ª chamada"

    def test_faq_e_acionada_pelo_servidor_quando_o_modelo_pula_a_ferramenta(self):
        """Rede de segurança do grounding.

        O `tool_choice="required"` é ignorado pelo Ollama, e em ~10% dos turnos
        o modelo responde de memória — chegando a negar que a clínica tenha
        estacionamento. Quando isso acontece e existe FAQ relevante, o servidor
        consulta por conta própria e a resposta é refeita em cima do dado real.
        """

        class FaqFalsa(_ToolFalsa):
            name = "buscar_faq"

            def execute(self, **kwargs):
                return {"encontrou": True, "resultados": [{"faq_id": 1, "resposta": "R$ 350,00"}]}

        cliente = FakeLLMClient(
            respostas=[RespostaLLM(texto="Não tenho informação sobre preços.")],
            fragmentos=[FragmentoStream.token("A consulta custa R$ 350,00.")],
        )
        conversa = uuid.uuid4()
        servico = ChatService(cliente=cliente, registry=ToolRegistry([FaqFalsa()]))
        pares = _eventos(servico.responder(pergunta="Quanto custa?", conversa_id=conversa))

        assert _texto(pares) == "A consulta custa R$ 350,00."
        assert InteracaoChat.objects.get(conversa_id=conversa).tools_usadas == [
            "buscar_faq:fallback"
        ]

    def test_fallback_nao_dispara_sem_faq_relevante(self):
        """Saudação e agradecimento não podem virar consulta ao FAQ."""

        class FaqVazia(_ToolFalsa):
            name = "buscar_faq"

            def execute(self, **kwargs):
                return {"encontrou": False, "resultados": []}

        cliente = FakeLLMClient(respostas=[RespostaLLM(texto="Olá! Como ajudo?")])
        pares = self._rodar(cliente, registry=ToolRegistry([FaqVazia()]), pergunta="Bom dia!")

        assert _texto(pares) == "Olá! Como ajudo?"
        assert cliente.chamadas_stream == []

    def test_com_tool_executa_e_streama_a_resposta_final(self):
        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_slots")])],
            fragmentos=[FragmentoStream.token("Temos "), FragmentoStream.token("vagas.")],
        )
        pares = self._rodar(cliente)

        assert _texto(pares) == "Temos vagas."
        assert ("status", "Consultando a agenda…") in pares

    def test_slot_id_nao_chega_ao_paciente_nem_ao_historico(self):
        """A tool precisa do id; a frase, não. E o registro alimenta o histórico
        do próximo turno — guardar o id sujo faria o modelo repeti-lo."""
        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_slots")])],
            fragmentos=[
                FragmentoStream.token("09:00 com Dr. Bruno "),
                FragmentoStream.token("(slot"),
                FragmentoStream.token("_id 1)"),
                FragmentoStream.token(". Confirma?"),
            ],
        )
        conversa = uuid.uuid4()
        servico = ChatService(cliente=cliente, registry=ToolRegistry([_ToolFalsa()]))
        pares = _eventos(servico.responder(pergunta="Tem horário?", conversa_id=conversa))

        assert _texto(pares) == "09:00 com Dr. Bruno. Confirma?"
        assert "slot_id" not in InteracaoChat.objects.get(conversa_id=conversa).resposta

    def test_sempre_termina_com_close(self):
        """Sem `close`, o EventSource reconecta em ~3s e reexecuta o turno."""
        cliente = FakeLLMClient(respostas=[RespostaLLM(texto="oi")])
        assert self._rodar(cliente)[-1][0] == "close"

    def test_llm_indisponivel_vira_erro_amigavel_e_fecha(self):
        cliente = FakeLLMClient(respostas=[LLMIndisponivelError("Serviço indisponível.")])
        pares = self._rodar(cliente)

        assert [n for n, _ in pares][-2:] == ["erro", "close"]

    def test_erro_inesperado_nao_vaza_detalhe_tecnico(self):
        cliente = FakeLLMClient(respostas=[RuntimeError("dsn=oracle://user:senha@host")])
        pares = self._rodar(cliente)
        mensagens = [d for n, d in pares if n == "erro"]

        assert mensagens
        assert "senha" not in mensagens[0]
        assert "oracle://" not in mensagens[0]

    def test_raciocinio_do_modelo_nao_vira_resposta(self):
        """Modelo com "thinking" emite raciocínio em fragmento próprio. Se ele
        vazar como token, o paciente lê o rascunho em inglês."""
        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_slots")])],
            fragmentos=[
                FragmentoStream.pensando("Okay, the user wants"),
                FragmentoStream.token("Temos vagas."),
            ],
        )
        assert _texto(self._rodar(cliente)) == "Temos vagas."

    def test_guardrail_responde_sem_chamar_o_modelo(self):
        cliente = FakeLLMClient(respostas=[RespostaLLM(texto="NAO DEVERIA SER USADO")])
        pares = self._rodar(cliente, pergunta="Me dá uma receita de colírio")

        assert "NAO DEVERIA" not in _texto(pares)
        assert "oftalmologista" in _texto(pares)

    def test_turno_e_registrado_para_auditoria(self):
        cliente = FakeLLMClient(
            respostas=[
                RespostaLLM(
                    tool_calls=[ToolCall(id="c1", nome="buscar_slots")],
                    tokens_entrada=10,
                    tokens_saida=5,
                )
            ],
            fragmentos=[FragmentoStream.token("Temos vagas.")],
        )
        conversa = uuid.uuid4()
        servico = ChatService(cliente=cliente, registry=ToolRegistry([_ToolFalsa()]))
        list(servico.responder(pergunta="Tem horário?", conversa_id=conversa))

        registro = InteracaoChat.objects.get(conversa_id=conversa)
        assert registro.tools_usadas == ["buscar_slots"]
        assert registro.resposta == "Temos vagas."
        assert registro.latencia_ms >= 0

    def test_faq_ids_ficam_registrados_como_rastro_de_grounding(self):
        class FaqFalsa(_ToolFalsa):
            name = "buscar_faq"

            def execute(self, **kwargs):
                return {"encontrou": True, "resultados": [{"faq_id": 7, "resposta": "x"}]}

        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_faq")])],
            fragmentos=[FragmentoStream.token("Sim.")],
        )
        conversa = uuid.uuid4()
        servico = ChatService(cliente=cliente, registry=ToolRegistry([FaqFalsa()]))
        list(servico.responder(pergunta="atende convênio?", conversa_id=conversa))

        assert InteracaoChat.objects.get(conversa_id=conversa).faq_ids == [7]

    def test_alucinacao_e_marcada_no_registro(self):
        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_slots")])],
            fragmentos=[FragmentoStream.token("Temos às 14:00.")],
        )
        conversa = uuid.uuid4()
        servico = ChatService(
            cliente=cliente, registry=ToolRegistry([_ToolFalsa({"slots": [{"hora": "09:00"}]})])
        )
        list(servico.responder(pergunta="Tem horário?", conversa_id=conversa))

        assert InteracaoChat.objects.get(conversa_id=conversa).alucinacao_detectada is True

    def test_resultado_da_tool_vai_para_o_modelo_no_formato_do_protocolo(self):
        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_slots")])],
            fragmentos=[FragmentoStream.token("ok")],
        )
        servico = ChatService(cliente=cliente, registry=ToolRegistry([_ToolFalsa()]))
        list(servico.responder(pergunta="Tem horário?", conversa_id=uuid.uuid4()))

        enviadas = cliente.chamadas_stream[-1].mensagens
        papeis = [m["role"] for m in enviadas]

        # O assistant que pediu a ferramenta precisa vir ANTES do resultado, e
        # com o mesmo id — senão o provedor não associa resposta a pedido.
        assert papeis.index("assistant") < papeis.index("tool")
        tool_msg = next(m for m in enviadas if m["role"] == "tool")
        assert tool_msg["tool_call_id"] == "c1"
        json.loads(tool_msg["content"])  # precisa ser JSON válido

    def test_schemas_seguem_na_chamada_final(self):
        """Omitir `tools` na 2ª chamada degrada a decisão do turno seguinte —
        medido em 0/4 contra 4/4."""
        cliente = FakeLLMClient(
            respostas=[RespostaLLM(tool_calls=[ToolCall(id="c1", nome="buscar_slots")])],
            fragmentos=[FragmentoStream.token("ok")],
        )
        servico = ChatService(cliente=cliente, registry=ToolRegistry([_ToolFalsa()]))
        list(servico.responder(pergunta="Tem horário?", conversa_id=uuid.uuid4()))

        assert cliente.chamadas_stream[-1].nomes_tools == ["buscar_slots"]

"""Orquestração de um turno de conversa.

Produz eventos SSE, não texto: quem consome é a view, que só repassa. Manter o
serviço como gerador é o que permite a UI mostrar progresso enquanto as
ferramentas rodam, em vez de esperar a resposta inteira.

Anatomia de um turno
--------------------
1. ``status`` imediato — o browser assume a conexão como aberta e o usuário vê
   feedback antes de qualquer inferência.
2. Chamada **não-streaming** com as ferramentas: descobre *qual* o modelo quer.
3. Execução das ferramentas, com ``status`` antes de cada uma.
4. Chamada **em streaming** para a resposta final.
5. Persistência de :class:`~apps.chatbot.models.InteracaoChat` e ``close``.

Grounding
---------
O modelo nunca é a fonte do dado — ele só verbaliza o que a ferramenta trouxe
(princípio "chatbot grounded" do ``README.md``). Duas defesas complementam o
prompt, que sozinho é placebo num modelo de 3B:

- **Atalho sem ferramenta.** Quando o modelo responde sem chamar nada, o texto
  já veio da primeira chamada e é reaproveitado. Além de cortar a latência pela
  metade, evita uma segunda geração que poderia introduzir dado inventado.
- **Auditoria pós-geração.** :func:`detectar_alucinacao` compara horários e
  nomes de médico citados no texto com o que as ferramentas devolveram. O
  resultado vai para ``InteracaoChat.alucinacao_detectada``, e a taxa é a
  métrica de qualidade que o projeto leva para a banca.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from django.conf import settings

from apps.chatbot import guardrails, sse
from apps.chatbot.models import InteracaoChat
from apps.chatbot.prompts import SYSTEM_PROMPT, montar_mensagens
from apps.chatbot.services.llm import get_llm_client
from apps.chatbot.services.llm.base import LLMClient, LLMIndisponivelError, RespostaLLM
from apps.chatbot.tools import ToolRegistry, construir_registry

logger = logging.getLogger(__name__)

MSG_ERRO_GENERICO = (
    "Desculpe, tive um problema para responder agora. "
    "Você pode tentar de novo, ou falar com a recepção pelo (51) 3000-0000."
)

# Rótulo mostrado enquanto cada ferramenta roda. Sem isso a tela fica parada
# durante a query, e o usuário não distingue "trabalhando" de "travou".
ROTULOS_TOOL = {
    "listar_especialidades_disponiveis": "Consultando as especialidades…",
    "buscar_slots": "Consultando a agenda…",
    "buscar_faq": "Procurando na base de informações…",
}

# Fatia usada ao reemitir texto já pronto (atalho sem ferramenta). Palavra a
# palavra dá a sensação de digitação sem custar uma segunda geração.
_PALAVRAS = re.compile(r"\S+\s*")

# Grupos não-capturantes de propósito: com grupo capturante, `findall` devolve
# o grupo em vez do trecho inteiro, e a comparação com a fonte fica errada.
_HORARIO = re.compile(r"\b(?:[01]?\d|2[0-3])[:h][0-5]\d\b")
_MEDICO = re.compile(r"\bDra?\.\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+)*")


def detectar_alucinacao(texto: str, resultados_tools: Sequence[str]) -> list[str]:
    """Devolve horários e médicos citados no texto que nenhuma ferramenta trouxe.

    Heurística deliberadamente simples e conservadora: só acusa o que é
    verificável de forma objetiva. Não tenta julgar afirmação livre — para isso
    existem os testes adversariais da S5-32.

    Args:
        texto: Resposta final do modelo.
        resultados_tools: JSONs devolvidos pelas ferramentas neste turno.

    Returns:
        Lista de trechos suspeitos. Vazia quando tudo que foi citado tem
        respaldo — o caso esperado.
    """
    if not texto:
        return []
    # "09h00" e "09:00" são a mesma informação; a ferramenta devolve um formato
    # e o modelo costuma reescrever no outro. Normalizar evita falso positivo.
    fonte = " ".join(resultados_tools).replace("h", ":")
    suspeitos = [
        trecho
        for padrao in (_HORARIO, _MEDICO)
        for trecho in padrao.findall(texto)
        if trecho.replace("h", ":") not in fonte
    ]
    return list(dict.fromkeys(suspeitos))


class ChatService:
    """Executa um turno de conversa e emite os eventos SSE correspondentes."""

    def __init__(
        self,
        cliente: LLMClient | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        """Args são injetáveis para o teste rodar sem rede nem banco."""
        self._cliente = cliente or get_llm_client()
        self._registry = registry or construir_registry()

    def responder(
        self,
        pergunta: str,
        conversa_id: uuid.UUID,
        historico: Sequence[dict[str, str]] = (),
        sequencia: int = 1,
    ) -> Iterator[str]:
        """Processa a pergunta e produz o stream de eventos SSE.

        Nunca levanta exceção: qualquer falha vira ``event: erro`` seguido de
        ``event: close``. O status HTTP já foi enviado como 200 quando o
        primeiro byte saiu, então não há como transformar isso em 500 — e uma
        conexão encerrada sem ``close`` faria o browser reexecutar o turno.
        """
        inicio = time.monotonic()
        registro = _RegistroTurno(conversa_id=conversa_id, sequencia=sequencia, pergunta=pergunta)

        try:
            yield sse.KEEPALIVE
            yield sse.status("Pensando…")
            yield from self._executar(pergunta, historico, registro)
        except LLMIndisponivelError as exc:
            logger.warning("LLM indisponível na conversa %s: %s", conversa_id, exc)
            registro.erro = str(exc)
            yield sse.erro(str(exc))
        except Exception:  # noqa: BLE001 — nada pode escapar de um gerador SSE
            logger.exception("Falha inesperada na conversa %s", conversa_id)
            registro.erro = "erro inesperado"
            yield sse.erro(MSG_ERRO_GENERICO)
        finally:
            registro.latencia_ms = int((time.monotonic() - inicio) * 1000)
            self._persistir(registro)
            yield sse.fechar()

    def _executar(
        self,
        pergunta: str,
        historico: Sequence[dict[str, str]],
        registro: _RegistroTurno,
    ) -> Iterator[str]:
        # Guardrail determinístico antes de qualquer inferência. Pedido de
        # conduta médica e sinal de urgência têm resposta fixa: não dependem do
        # humor do modelo, não podem ser contornados por prompt injection, e
        # ainda economizam uma chamada. Ver `apps/chatbot/guardrails.py`.
        interceptado = guardrails.interceptar(pergunta)
        if interceptado is not None:
            logger.info("Turno interceptado por guardrail: %s", interceptado.motivo)
            yield sse.status("")
            for fragmento in _PALAVRAS.findall(interceptado.resposta):
                yield sse.token(fragmento)
            registro.resposta = interceptado.resposta
            registro.tools_usadas.append(f"guardrail:{interceptado.motivo}")
            return

        mensagens = montar_mensagens(SYSTEM_PROMPT, historico, pergunta)
        schemas = self._registry.schemas()

        # `tool_choice="required"` é passado, mas **não confie nele**: o Ollama
        # 0.30.10 o aceita e ignora — medido, 0/5 tanto com `required` quanto
        # com `auto` num teste isolado. Fica aqui porque é o valor correto do
        # protocolo e passa a valer sozinho quando o provedor implementar.
        #
        # Com as três ferramentas registradas o modelo chama alguma em ~90% dos
        # turnos (18/20 medido). Os 10% restantes são cobertos pelo fallback
        # logo abaixo — não por prompt: acrescentar uma instrução de reforço
        # PIOROU o índice (12/16 contra 14/16), coerente com o resto do que se
        # mediu sobre tamanho de prompt neste modelo.
        decisao = self._cliente.conversar(mensagens, tools=schemas, tool_choice="required")
        registro.somar_tokens(decisao)

        if not decisao.pediu_tool:
            # Rede de segurança do grounding: o modelo decidiu responder de
            # memória. Antes de aceitar isso, o **servidor** consulta o FAQ por
            # conta própria. Se houver resposta relevante, o turno continua como
            # se a ferramenta tivesse sido chamada.
            #
            # É o que impede o pior caso observado: o modelo afirmando "não
            # tenho informações sobre os preços" quando a FAQ tem o valor, ou
            # "não tem estacionamento" quando tem. Determinístico, e custa uma
            # busca vetorial de menos de 1 ms.
            forcada = self._buscar_faq_de_seguranca(pergunta)
            if forcada is not None:
                logger.info("Modelo não chamou ferramenta; FAQ acionada pelo servidor.")
                yield sse.status("Procurando na base de informações…")
                registro.registrar_tool("buscar_faq:fallback", forcada)
                mensagens.append(
                    {"role": "system", "content": f"Dados da clínica para responder: {forcada}"}
                )
                yield from self._streamar_resposta(mensagens, schemas, registro)
                return

            # Texto já pronto e sem FAQ relevante (saudação, agradecimento,
            # pedido de esclarecimento). Uma segunda chamada só dobraria a
            # latência e abriria espaço para inventar algo que ninguém pediu.
            yield sse.status("")
            for fragmento in _PALAVRAS.findall(decisao.texto):
                yield sse.token(fragmento)
            registro.resposta = decisao.texto
            registro.alucinacoes = detectar_alucinacao(decisao.texto, registro.resultados_tools)
            return

        mensagens.append(_mensagem_assistente(decisao))
        for chamada in decisao.tool_calls:
            yield sse.status(ROTULOS_TOOL.get(chamada.nome, "Consultando…"))
            resultado = self._registry.executar(chamada.nome, chamada.argumentos)
            registro.registrar_tool(chamada.nome, resultado)
            mensagens.append({"role": "tool", "tool_call_id": chamada.id, "content": resultado})

        yield from self._streamar_resposta(mensagens, schemas, registro)

    def _streamar_resposta(
        self,
        mensagens: list[dict[str, Any]],
        schemas: list[dict[str, Any]],
        registro: _RegistroTurno,
    ) -> Iterator[str]:
        """Faz a chamada final em streaming e emite os tokens.

        Os `schemas` seguem na chamada mesmo sem poder ser usados aqui: omiti-los
        degrada a decisão de ferramenta do **turno seguinte**.
        """
        yield sse.status("Escrevendo a resposta…")
        partes: list[str] = []
        primeiro = True
        for fragmento in self._cliente.stream(mensagens, tools=schemas):
            if fragmento.tipo == "pensando":
                # Raciocínio interno: vira sinal de atividade, nunca resposta.
                yield sse.status("Pensando…")
                continue
            if primeiro:
                yield sse.status("")  # apaga o indicador ao primeiro token real
                primeiro = False
            partes.append(fragmento.texto)
            yield sse.token(fragmento.texto)

        registro.resposta = "".join(partes)
        registro.alucinacoes = detectar_alucinacao(registro.resposta, registro.resultados_tools)
        if registro.alucinacoes:
            logger.warning(
                "Possível alucinação na conversa %s: %s", registro.conversa_id, registro.alucinacoes
            )

    def _buscar_faq_de_seguranca(self, pergunta: str) -> str | None:
        """Consulta o FAQ sem passar pelo modelo. ``None`` se nada for relevante.

        Usado quando o modelo decide responder de memória. O corte de relevância
        é o mesmo da ferramenta, então saudação e agradecimento não disparam
        nada — só pergunta que de fato tem resposta na base.
        """
        try:
            bruto = self._registry.executar("buscar_faq", {"pergunta": pergunta})
        except Exception:  # noqa: BLE001 — rede de segurança não pode derrubar o turno
            logger.exception("Falha no fallback de FAQ")
            return None
        try:
            dados = json.loads(bruto)
        except ValueError:
            return None
        return bruto if dados.get("encontrou") else None

    def _persistir(self, registro: _RegistroTurno) -> None:
        """Grava a auditoria do turno. Nunca derruba a resposta já entregue."""
        try:
            InteracaoChat.objects.create(**registro.como_campos())
        except Exception:  # noqa: BLE001
            logger.exception("Não foi possível registrar InteracaoChat")


class _RegistroTurno:
    """Acumula o que vira uma linha de ``InteracaoChat``."""

    def __init__(self, conversa_id: uuid.UUID, sequencia: int, pergunta: str) -> None:
        self.conversa_id = conversa_id
        self.sequencia = sequencia
        self.pergunta = pergunta
        self.resposta = ""
        self.erro = ""
        self.latencia_ms = 0
        self.tokens_entrada = 0
        self.tokens_saida = 0
        self.tools_usadas: list[str] = []
        self.resultados_tools: list[str] = []
        self.alucinacoes: list[str] = []

    def somar_tokens(self, resposta: RespostaLLM) -> None:
        self.tokens_entrada += resposta.tokens_entrada or 0
        self.tokens_saida += resposta.tokens_saida or 0

    def registrar_tool(self, nome: str, resultado: str) -> None:
        self.tools_usadas.append(nome)
        self.resultados_tools.append(resultado)

    def faq_ids(self) -> list[int]:
        """IDs de FAQ que embasaram a resposta — rastro de grounding."""
        ids: list[int] = []
        for bruto in self.resultados_tools:
            try:
                dados = json.loads(bruto)
            except (TypeError, ValueError):
                continue
            for item in dados.get("resultados", []) if isinstance(dados, dict) else []:
                if isinstance(item, dict) and "faq_id" in item:
                    ids.append(item["faq_id"])
        return ids

    def como_campos(self) -> dict[str, Any]:
        return {
            "conversa_id": self.conversa_id,
            "sequencia": self.sequencia,
            "pergunta": self.pergunta,
            "resposta": self.resposta,
            "tools_usadas": self.tools_usadas,
            "faq_ids": self.faq_ids(),
            "modelo": settings.LLM_MODEL,
            "tokens_entrada": self.tokens_entrada or None,
            "tokens_saida": self.tokens_saida or None,
            "latencia_ms": self.latencia_ms,
            "alucinacao_detectada": bool(self.alucinacoes),
            "erro": self.erro,
        }


def _mensagem_assistente(decisao: RespostaLLM) -> dict[str, Any]:
    """Reconstrói o turno do assistente que pediu as ferramentas.

    Precisa voltar para o modelo **antes** das mensagens ``role="tool"``, com
    os mesmos ``id``. Sem isso o provedor não associa resultado a pedido e
    rejeita a conversa.
    """
    return {
        "role": "assistant",
        "content": decisao.texto or "",
        "tool_calls": [
            {
                "id": chamada.id,
                "type": "function",
                "function": {
                    "name": chamada.nome,
                    "arguments": json.dumps(chamada.argumentos, ensure_ascii=False),
                },
            }
            for chamada in decisao.tool_calls
        ],
    }

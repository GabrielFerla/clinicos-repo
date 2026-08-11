"""Cliente de LLM contra o Ollama local, pelo endpoint compatível com a OpenAI.

O Ollama expõe ``/v1/chat/completions`` com o mesmo contrato da OpenAI, então
usamos o SDK ``openai`` como transporte — **não** há chamada a serviço pago
(ver ``infra/django/requirements/base.txt`` e ``docs/CHAT_MVP.md``).

Três cuidados que este módulo existe para resolver
--------------------------------------------------
1. **``delta.reasoning``.** Modelos com "thinking" (família ``qwen3``) emitem o
   raciocínio num campo separado, com ``delta.content`` vazio. Esse campo
   **não existe** no tipo ``ChoiceDelta`` do SDK: ele chega em
   ``model_extra`` porque o modelo pydantic é ``extra="allow"``. O spike fazia
   ``if not fragmento: continue`` e descartava tudo — resultado: 11s de tela em
   branco. Aqui o raciocínio vira ``FragmentoStream(tipo="pensando")``, que a
   view usa como sinal de status e **nunca** como texto de resposta. O modelo
   atual (``qwen2.5:3b``) não emite o campo; o tratamento existe para o código
   sobreviver a uma troca de modelo. Ver ``docs/CHAT_MVP.md`` §4.2.

2. **Vazamento de erro.** Qualquer falha do provedor vira
   :class:`~apps.chatbot.services.llm.base.LLMIndisponivelError` com mensagem
   amigável. ``str(exc)`` do SDK contém a URL base (``host.docker.internal``,
   porta) e caminhos internos — vai só para o log.

3. **Retry.** ``max_retries=0`` de propósito: o Ollama roda com ``-np 1`` e
   **serializa** requests (``docs/CHAT_MVP.md`` §4.4). Um retry automático
   depois de timeout não conserta nada — só enfileira outra inferência
   completa atrás da que ainda está rodando, dobrando a espera do paciente.

4. **A chamada final mantém ``tools`` com ``tool_choice="none"``.** Medido
   neste ambiente com ``qwen2.5:3b``, e o número é agressivo: uma decisão de
   tool feita logo depois de um request **sem** ``tools`` acerta **0 de 4** —
   o modelo pula a ferramenta e responde "Sim, tem horários disponíveis para
   Retina" de cabeça, inventando disponibilidade. Duas decisões de tool
   seguidas, sem request sem-tools no meio, acertam **4 de 4**. Reenviando os
   schemas na chamada de streaming (com ``tool_choice="none"``, que impede o
   modelo de chamá-las), volta para **4 de 4**.

   A causa provável é o reuso de cache de prompt do Ollama: o template do
   modelo renderiza as definições de ferramenta **dentro** da mensagem de
   sistema, então omiti-las muda o prefixo e o slot único do servidor
   reaproveita KV de um contexto onde não havia ferramenta alguma.

   Isso importa porque a sequência real de um turno é *decisão de tool →
   resposta em streaming → decisão de tool do turno seguinte*: sem esse
   cuidado, **todo turno a partir do segundo** cai no caso ruim. É o modo de
   falha que ``docs/RISCOS.md`` chama de R4, e o que ``docs/CHAT_MVP.md``
   §Bloco 4 já previa ao especificar ``tool_choice="none"`` na fase 3.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from django.conf import settings
from openai import OpenAI, OpenAIError

from .base import FragmentoStream, LLMIndisponivelError, RespostaLLM, ToolCall

logger = logging.getLogger(__name__)

# Mensagem única para qualquer falha de provedor. Genérica de propósito: ela
# chega ao paciente. O que aconteceu de fato fica no log.
MENSAGEM_INDISPONIVEL = (
    "Não consegui falar com o assistente agora. Tente de novo em instantes ou "
    "fale com a nossa equipe pelo telefone da clínica."
)

# Campos onde provedores compatíveis com a OpenAI colocam o raciocínio.
# ``reasoning`` é o que o Ollama usa; ``reasoning_content`` aparece em vLLM e
# em builds do DeepSeek. Nenhum dos dois existe no tipo ``ChoiceDelta``.
CAMPOS_RACIOCINIO = ("reasoning", "reasoning_content")


def _ler_campo(delta: Any, nome: str) -> Any:
    """Lê um campo do delta sem assumir que ele existe no tipo do SDK.

    Cobre as três formas em que um delta chega: modelo pydantic com o campo
    declarado (atributo), modelo pydantic com campo extra (``model_extra``) e
    ``dict`` cru (provedores que fogem do SDK). Devolve ``None`` quando o campo
    não está presente em nenhuma delas — nunca levanta.
    """
    if isinstance(delta, dict):
        return delta.get(nome)

    extras = getattr(delta, "model_extra", None)
    if isinstance(extras, dict) and nome in extras:
        return extras[nome]

    return getattr(delta, nome, None)


def extrair_raciocinio(delta: Any) -> str:
    """Extrai o texto de raciocínio do delta, ou ``""`` se não houver.

    Função de módulo (e não método) para ser testável sem cliente nem rede —
    é o parsing que o spike errou e que precisa de teste de regressão.
    """
    for campo in CAMPOS_RACIOCINIO:
        valor = _ler_campo(delta, campo)
        if isinstance(valor, str) and valor:
            return valor
    return ""


def extrair_conteudo(delta: Any) -> str:
    """Extrai o texto de resposta do delta, ou ``""`` se não houver.

    ``content`` chega como ``None`` (não ``""``) em vários chunks — no primeiro,
    que só traz ``role``, e em todos os chunks de um modelo que está pensando.
    """
    valor = _ler_campo(delta, "content")
    return valor if isinstance(valor, str) else ""


class OllamaLLMClient:
    """Implementação de ``LLMClient`` para o Ollama local.

    Todos os parâmetros têm default vindo de ``settings`` — a instanciação
    normal é ``OllamaLLMClient()``. Os argumentos existem para teste e para o
    dia em que houver mais de um modelo em uso.

    Args:
        base_url: Endpoint compatível com OpenAI. Default ``LLM_BASE_URL``.
        api_key: O Ollama ignora o valor, mas o SDK recusa string vazia.
        modelo: Default ``LLM_MODEL``. Use um modelo **sem thinking**.
        temperatura: Default ``LLM_TEMPERATURE`` (0.1 — resposta operacional,
            não criativa).
        timeout: Segundos. Default ``LLM_TIMEOUT_SEGUNDOS``.
        cliente: Injeta um transporte pronto (usado nos testes). Quando
            informado, os demais argumentos de conexão são ignorados.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        modelo: str | None = None,
        temperatura: float | None = None,
        timeout: float | None = None,
        cliente: Any | None = None,
    ) -> None:
        self.modelo = modelo or settings.LLM_MODEL
        self.temperatura = temperatura if temperatura is not None else settings.LLM_TEMPERATURE
        self.timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SEGUNDOS
        self._cliente = cliente or OpenAI(
            base_url=base_url or settings.LLM_BASE_URL,
            api_key=api_key or settings.LLM_API_KEY,
            timeout=self.timeout,
            max_retries=0,  # ver docstring do módulo: Ollama serializa requests
        )

    # -- API pública --------------------------------------------------------

    def conversar(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> RespostaLLM:
        """Chamada não-streaming; devolve texto e/ou ``tool_calls``."""
        bruta = self._criar(mensagens, tools, stream=False, tool_choice="auto")

        if not bruta.choices:
            logger.error("Ollama devolveu resposta sem choices (modelo=%s).", self.modelo)
            raise LLMIndisponivelError(MENSAGEM_INDISPONIVEL)

        mensagem = bruta.choices[0].message
        usage = getattr(bruta, "usage", None)

        return RespostaLLM(
            texto=getattr(mensagem, "content", None) or "",
            tool_calls=self._converter_tool_calls(getattr(mensagem, "tool_calls", None)),
            tokens_entrada=getattr(usage, "prompt_tokens", None),
            tokens_saida=getattr(usage, "completion_tokens", None),
            modelo=getattr(bruta, "model", None) or self.modelo,
        )

    def stream(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[FragmentoStream]:
        """Resposta em streaming — a resposta **final** do turno.

        Passe os mesmos ``tools`` da chamada de decisão. Eles vão com
        ``tool_choice="none"``: o modelo não pode chamar ferramenta aqui, mas
        os schemas continuam no prompt. Omiti-los derruba a decisão de tool do
        turno seguinte de 4/4 para 0/4 — ver item 4 da docstring do módulo.

        Não é um generator function: a abertura do stream acontece **aqui**,
        de forma que falha de conexão levante antes de qualquer ``yield``. Só
        o consumo dos chunks é preguiçoso.
        """
        bruto = self._criar(mensagens, tools, stream=True, tool_choice="none")
        return self._iterar(bruto)

    # -- Internos -----------------------------------------------------------

    def _criar(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        stream: bool,
        tool_choice: str,
    ) -> Any:
        """Monta os kwargs e chama o provedor, traduzindo qualquer erro."""
        kwargs: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensagens,
            "temperature": self.temperatura,
            "stream": stream,
        }
        # ``tools=None`` explícito serializa ``"tools": null``, que alguns
        # servidores rejeitam — quando não há ferramenta, a chave some.
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        try:
            return self._cliente.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            # ``exc`` traz base_url e headers; por isso só o log recebe.
            logger.exception("Falha ao chamar o LLM (modelo=%s, stream=%s).", self.modelo, stream)
            raise LLMIndisponivelError(MENSAGEM_INDISPONIVEL) from exc

    def _iterar(self, bruto: Any) -> Iterator[FragmentoStream]:
        """Traduz os chunks do SDK em :class:`FragmentoStream`."""
        try:
            for chunk in bruto:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    # Chunk final com ``usage`` e ``choices`` vazio.
                    continue

                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                # Raciocínio primeiro: quando existe, é o que chega antes do
                # texto — e é o que mantém a tela viva enquanto o modelo pensa.
                raciocinio = extrair_raciocinio(delta)
                if raciocinio:
                    yield FragmentoStream.pensando(raciocinio)

                conteudo = extrair_conteudo(delta)
                if conteudo:
                    yield FragmentoStream.token(conteudo)
        except OpenAIError as exc:
            logger.exception("Stream do LLM interrompido (modelo=%s).", self.modelo)
            raise LLMIndisponivelError(MENSAGEM_INDISPONIVEL) from exc

    def _converter_tool_calls(self, brutos: Any) -> list[ToolCall]:
        """Converte ``tool_calls`` do SDK, desserializando os argumentos.

        Argumento em JSON inválido vira ``{}`` em vez de derrubar o turno: o
        modelo é pequeno e erra a serialização de vez em quando. A tool recebe
        o dicionário vazio, falha a validação de argumentos obrigatórios e
        devolve um erro que o modelo consegue ler e corrigir na próxima
        iteração — degradação melhor que uma exceção no meio do chat.
        """
        if not brutos:
            return []

        convertidos: list[ToolCall] = []
        for bruto in brutos:
            funcao = getattr(bruto, "function", None)
            nome = getattr(funcao, "name", "") or ""
            crus = getattr(funcao, "arguments", "") or ""

            try:
                argumentos = json.loads(crus) if crus else {}
            except (TypeError, ValueError):
                logger.warning("Argumentos inválidos na tool_call %r; tratando como vazio.", nome)
                argumentos = {}

            if not isinstance(argumentos, dict):
                logger.warning("Argumentos da tool_call %r não são objeto JSON.", nome)
                argumentos = {}

            convertidos.append(
                ToolCall(id=getattr(bruto, "id", "") or "", nome=nome, argumentos=argumentos)
            )
        return convertidos

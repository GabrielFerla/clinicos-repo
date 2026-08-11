"""Contrato da camada de LLM — tipos de dado, Protocol e erro.

Este módulo é a fronteira que isola o resto do ClinicOS do provedor de
inferência. O ``ChatService`` depende **só** do que está aqui; trocar Ollama
por Anthropic (débito registrado em ``docs/STATUS.md``) é escrever outra
implementação do ``LLMClient``, não reescrever o serviço.

Nada neste pacote importa models do Django, de propósito: os testes da camada
de IA rodam no CI sem banco e sem rede.

Por que dois métodos e não um
-----------------------------
O turno de chat do ClinicOS faz **duas** chamadas ao modelo, com necessidades
opostas (ver ``docs/CHAT_MVP.md`` §Bloco 4):

1. :meth:`LLMClient.conversar` — **não-streaming**, com ``tools``. Só interessa
   *qual* ferramenta o modelo escolheu; streamar isso não traz nada para a
   tela e complica o parsing de ``tool_calls`` fragmentados em deltas.
2. :meth:`LLMClient.stream` — **streaming**, resposta final. Aqui o que importa
   é o tempo até o primeiro token visível (TTFT), a métrica de
   ``docs/METRICAS.md``.

Por que ``FragmentoStream`` tem tipo
------------------------------------
Modelos com "thinking" emitem o raciocínio num campo separado
(``delta.reasoning``), com ``delta.content`` vazio. O spike descartava
fragmentos vazios (``if not fragmento: continue``) e a tela ficava 11s em
branco. O tipo do fragmento deixa a view distinguir "está pensando" (feedback
de status) de "isto é a resposta" (texto para o paciente) — e o código
sobrevive a uma troca de modelo. Ver ``docs/CHAT_MVP.md`` §4.2.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# Tipos de fragmento emitidos por :meth:`LLMClient.stream`.
#
# - ``token``   → texto da resposta, vai para o paciente (após escape de HTML).
# - ``pensando``→ raciocínio interno do modelo. **Nunca** exibir como resposta;
#   serve como sinal de "ainda estou processando".
TipoFragmento = Literal["token", "pensando"]


class LLMIndisponivelError(RuntimeError):
    """O provedor de LLM não respondeu (timeout, conexão recusada, erro HTTP).

    A mensagem desta exceção é **exibível ao usuário final**: nunca deve conter
    ``str(exc)`` do erro original, URL do provedor ou caminho de arquivo. O
    spike mandava ``str(exc)`` para o browser e vazava DSN e caminhos internos
    (ver ``docs/CHAT_MVP.md`` §Bloco 4, conserto 4). O detalhe técnico vai para
    o log, via ``logger.exception``.
    """


@dataclass(frozen=True)
class ToolCall:
    """Pedido de execução de ferramenta feito pelo modelo.

    Attributes:
        id: Identificador gerado pelo provedor. Precisa voltar como
            ``tool_call_id`` na mensagem ``role="tool"``, senão o modelo não
            associa o resultado ao pedido.
        nome: Nome da ferramenta (``buscar_slots``, ``buscar_faq``, ...).
        argumentos: Argumentos já desserializados. Vem como string JSON no
            protocolo; a implementação do cliente é quem converte. JSON
            inválido do modelo vira ``{}`` — a validação de argumento é
            responsabilidade da tool, que devolve erro amigável ao modelo.
    """

    id: str
    nome: str
    argumentos: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RespostaLLM:
    """Resposta completa (não-streaming) de uma chamada ao modelo.

    Attributes:
        texto: Conteúdo textual. Vazio quando o modelo optou por chamar tool.
        tool_calls: Ferramentas pedidas neste turno. Pode ter mais de uma.
        tokens_entrada: ``usage.prompt_tokens``, quando o provedor informa.
        tokens_saida: ``usage.completion_tokens``, quando o provedor informa.
        modelo: Modelo que de fato respondeu (nem sempre igual ao pedido).

    ``tokens_*`` são opcionais porque nem todo provedor devolve ``usage``.
    Quando vêm, alimentam ``InteracaoChat`` — é o número de custo por turno
    que ``docs/METRICAS.md`` cobra.
    """

    texto: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    modelo: str = ""

    @property
    def pediu_tool(self) -> bool:
        """``True`` se o modelo pediu ao menos uma ferramenta neste turno."""
        return bool(self.tool_calls)


@dataclass(frozen=True)
class FragmentoStream:
    """Um pedaço da resposta em streaming.

    ``tipo="token"`` é texto para o paciente; ``tipo="pensando"`` é raciocínio
    interno e **não** pode ser renderizado como resposta.
    """

    tipo: TipoFragmento
    texto: str

    @classmethod
    def token(cls, texto: str) -> FragmentoStream:
        """Atalho para fragmento de resposta."""
        return cls(tipo="token", texto=texto)

    @classmethod
    def pensando(cls, texto: str) -> FragmentoStream:
        """Atalho para fragmento de raciocínio (status, nunca resposta)."""
        return cls(tipo="pensando", texto=texto)


@runtime_checkable
class LLMClient(Protocol):
    """Interface mínima que o ``ChatService`` consome.

    ``Protocol`` (e não classe base abstrata) porque as implementações não
    compartilham código: o cliente Ollama fala HTTP, o fake devolve script.
    ``runtime_checkable`` permite ``isinstance(obj, LLMClient)`` nos testes —
    lembrando que ele só verifica a **presença** dos métodos, não as
    assinaturas.
    """

    def conversar(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> RespostaLLM:
        """Chamada não-streaming. Usada para decidir a chamada de ferramenta.

        Args:
            mensagens: Histórico no formato do protocolo OpenAI
                (``{"role": ..., "content": ...}``, mais ``tool_calls`` /
                ``tool_call_id`` nos turnos de ferramenta).
            tools: Schemas das ferramentas disponíveis. ``None`` desabilita
                tool use nesta chamada.

        Raises:
            LLMIndisponivelError: provedor fora do ar, timeout ou erro HTTP.
        """
        ...

    def stream(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[FragmentoStream]:
        """Resposta final em streaming, fragmento a fragmento.

        Falha de conexão é levantada **na chamada**, não na primeira iteração,
        para que o caller consiga distinguir "não conectou" de "quebrou no
        meio do stream" (onde parte do texto já foi enviada ao browser).

        Args:
            mensagens: Conversa completa, incluindo os resultados das tools já
                executadas neste turno.
            tools: **Passe os mesmos schemas da chamada de decisão.** Aqui eles
                não podem ser chamados (a implementação usa
                ``tool_choice="none"``); ficam no prompt porque omiti-los
                sabota a decisão de tool do *turno seguinte* — medido em
                0/4 contra 4/4, ver ``apps.chatbot.services.llm.ollama``.

        Raises:
            LLMIndisponivelError: provedor fora do ar, timeout ou erro HTTP —
                seja ao abrir o stream, seja durante o consumo.
        """
        ...

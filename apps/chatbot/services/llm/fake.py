"""Cliente de LLM scriptável — o que torna o ``ChatService`` testável no CI.

O loop de tool use (assistant pede tool → executa → 2ª chamada) é a parte do
chatbot com mais caminhos de erro: tool desconhecida, JSON de argumentos
inválido, tool que estoura, duas ``tool_calls`` no mesmo turno, provedor fora
do ar. Nenhum desses caminhos é testável contra um modelo real — a saída é
não-determinística e o Ollama nem existe no CI.

Aqui o teste **escreve o roteiro**: diz exatamente o que o modelo responde em
cada chamada e verifica o que o serviço fez com isso.

Uso típico::

    cliente = FakeLLMClient(
        respostas=[
            RespostaLLM(tool_calls=[ToolCall("c1", "buscar_slots", {"esp": "Retina"})]),
            RespostaLLM(texto="Temos estes horários:"),
        ],
        fragmentos=["Temos ", "estes ", "horários:"],
    )
    ...
    assert cliente.chamadas_conversar[1].mensagens[-1]["role"] == "tool"
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .base import FragmentoStream, RespostaLLM

# Roteiro default do provedor ``fake`` quando ninguém passou script: permite
# subir a aplicação inteira sem Ollama (dev sem GPU, CI, demo offline) e
# receber uma resposta coerente em vez de erro.
RESPOSTA_PADRAO = (
    "Sou o assistente de demonstração da clínica e estou rodando sem modelo de "
    "linguagem no momento."
)


class FakeLLMEsgotadoError(RuntimeError):
    """O roteiro acabou e o código pediu mais uma resposta.

    Quase sempre significa que o serviço fez mais chamadas do que o teste
    previu — um loop de tool que não convergiu, por exemplo. Falhar alto aqui
    é melhor que devolver resposta vazia e o teste passar por acidente.
    """


@dataclass(frozen=True)
class ChamadaLLM:
    """Registro de uma chamada recebida pelo fake.

    ``mensagens`` é uma **cópia profunda** do que foi passado. Sem isso o
    registro seria inútil: o ``ChatService`` reaproveita e muta a mesma lista
    entre a 1ª e a 2ª chamada (append do assistant e do resultado da tool), e
    todas as chamadas registradas apontariam para o estado final.
    """

    mensagens: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    streaming: bool = False

    @property
    def nomes_tools(self) -> list[str]:
        """Nomes das ferramentas oferecidas nesta chamada."""
        return [t.get("function", {}).get("name", "") for t in self.tools or []]


@dataclass
class FakeLLMClient:
    """Implementação de ``LLMClient`` que devolve um roteiro fixo.

    Args:
        respostas: Devolvidas por :meth:`conversar`, uma por chamada, em ordem.
            Um item que seja ``Exception`` é **levantado** em vez de devolvido —
            é assim que se testa o caminho de ``LLMIndisponivelError``.
        fragmentos: Emitidos por :meth:`stream`. ``str`` é atalho para
            ``FragmentoStream.token``. Um ``Exception`` na lista é levantado no
            ponto em que aparece, simulando stream que quebra no meio (com
            parte do texto já enviada ao browser).
        erro_stream: Se definido, :meth:`stream` levanta na chamada, antes de
            qualquer fragmento — simula provedor fora do ar na abertura.
        modelo: Valor de ``RespostaLLM.modelo`` no roteiro default.

    Ao contrário de ``respostas``, ``fragmentos`` **não é consumido**: o mesmo
    roteiro sai a cada chamada de :meth:`stream`. Um turno faz no máximo um
    stream, e repetir é mais previsível que esgotar.
    """

    respostas: Sequence[RespostaLLM | Exception] = ()
    fragmentos: Sequence[FragmentoStream | str | Exception] = ()
    erro_stream: Exception | None = None
    modelo: str = "fake"

    chamadas_conversar: list[ChamadaLLM] = field(default_factory=list, init=False)
    chamadas_stream: list[ChamadaLLM] = field(default_factory=list, init=False)
    _proxima: int = field(default=0, init=False)

    # -- API pública --------------------------------------------------------

    def conversar(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> RespostaLLM:
        """Devolve a próxima resposta do roteiro e registra a chamada."""
        self.chamadas_conversar.append(self._registrar(mensagens, tools, streaming=False))

        if not self.respostas:
            return RespostaLLM(texto=RESPOSTA_PADRAO, modelo=self.modelo)

        if self._proxima >= len(self.respostas):
            raise FakeLLMEsgotadoError(
                f"FakeLLMClient recebeu {self._proxima + 1} chamadas de conversar(), "
                f"mas o roteiro tem só {len(self.respostas)} resposta(s)."
            )

        item = self.respostas[self._proxima]
        self._proxima += 1
        if isinstance(item, Exception):
            raise item
        return item

    def stream(
        self,
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[FragmentoStream]:
        """Emite o roteiro de fragmentos e registra a chamada.

        Levanta ``erro_stream`` **antes** do primeiro ``yield``, igual ao
        cliente real, onde a conexão é aberta na chamada e não na iteração.
        """
        self.chamadas_stream.append(self._registrar(mensagens, tools, streaming=True))

        if self.erro_stream is not None:
            raise self.erro_stream

        roteiro = self.fragmentos or [FragmentoStream.token(RESPOSTA_PADRAO)]
        return self._emitir(roteiro)

    # -- Auxiliares de asserção --------------------------------------------

    @property
    def total_chamadas(self) -> int:
        """Quantas vezes o cliente foi acionado, somando os dois métodos."""
        return len(self.chamadas_conversar) + len(self.chamadas_stream)

    @property
    def ultima_chamada(self) -> ChamadaLLM | None:
        """A chamada mais recente de qualquer um dos métodos, ou ``None``."""
        todas = self.chamadas_conversar + self.chamadas_stream
        return todas[-1] if todas else None

    # -- Internos -----------------------------------------------------------

    @staticmethod
    def _registrar(
        mensagens: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        streaming: bool,
    ) -> ChamadaLLM:
        return ChamadaLLM(
            mensagens=deepcopy(list(mensagens)),
            tools=deepcopy(list(tools)) if tools is not None else None,
            streaming=streaming,
        )

    @staticmethod
    def _emitir(
        roteiro: Sequence[FragmentoStream | str | Exception],
    ) -> Iterator[FragmentoStream]:
        for item in roteiro:
            if isinstance(item, Exception):
                raise item
            yield FragmentoStream.token(item) if isinstance(item, str) else item

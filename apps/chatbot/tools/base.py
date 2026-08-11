"""Contrato das ferramentas do chatbot e o registro que as despacha.

Uma "tool" é a única forma de o chatbot obter dado operacional. O princípio,
repetido em três documentos do projeto: *o LLM nunca inventa horário, médico ou
especialidade — tudo vem de query real*. O modelo escolhe **qual** ferramenta
chamar e com quais argumentos; quem executa é o servidor.

O formato do ``input_schema`` é o do protocolo OpenAI (usado também pelo
Ollama). Quando a migração para a Anthropic acontecer, o único ponto a reescrever
é :meth:`BaseTool.schema_openai` — as tools em si não mudam.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class ToolError(RuntimeError):
    """Falha esperada na execução de uma ferramenta.

    A mensagem volta **para o modelo**, não para o usuário: é o que permite ao
    chatbot dizer "não consegui consultar a agenda agora" em vez de travar.
    Nunca inclua stacktrace nem detalhe de conexão aqui.
    """


class BaseTool(ABC):
    """Ferramenta consultável pelo chatbot.

    Subclasses declaram ``name``, ``description`` e ``input_schema``, e
    implementam :meth:`execute`. O formato segue ``docs/ARQUITETURA.md``.

    A ``description`` não é documentação — é **prompt**. É por ela que um modelo
    pequeno decide se chama esta ferramenta ou outra, então escreva pensando em
    desambiguar das demais, não em explicar a implementação.
    """

    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Executa a ferramenta e devolve um dict serializável em JSON.

        O retorno vira o conteúdo da mensagem ``role="tool"``, ou seja, é lido
        pelo modelo. Prefira estruturas rasas e rótulos em português: o modelo
        copia o que recebe, e isso reduz erro de transcrição na resposta final.

        Raises:
            ToolError: falha esperada, com mensagem segura para o modelo.
        """

    def schema_openai(self) -> dict[str, Any]:
        """Devolve o schema no formato que a API espera em ``tools=[...]``."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    """Coleção de ferramentas disponíveis num turno.

    Instanciado por turno (e não como singleton de módulo) de propósito: o
    ``enum`` de especialidades do ``buscar_slots`` é montado a partir do banco,
    então o schema precisa refletir o estado atual — cadastrar uma
    especialidade nova não pode exigir restart.
    """

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def schemas(self) -> list[dict[str, Any]]:
        """Schemas de todas as ferramentas, para mandar em ``tools=[...]``."""
        return [tool.schema_openai() for tool in self._tools.values()]

    def nomes(self) -> list[str]:
        """Nomes registrados. Útil em log e em asserção de teste."""
        return list(self._tools)

    def executar(self, nome: str, argumentos: dict[str, Any]) -> str:
        """Executa a ferramenta pedida e devolve JSON pronto para o modelo.

        **Nunca levanta exceção.** Uma tool que falha, ou um nome que não
        existe, precisa virar um resultado que o modelo consiga verbalizar —
        senão o turno inteiro morre e o paciente vê uma tela de erro por causa
        de uma query lenta. Erro inesperado é logado com stacktrace e sai daqui
        como mensagem curta e segura.

        Args:
            nome: Nome pedido pelo modelo.
            argumentos: Argumentos já desserializados.

        Returns:
            String JSON. Em caso de falha, ``{"erro": "..."}``.
        """
        tool = self._tools.get(nome)
        if tool is None:
            # Acontece quando o modelo alucina um nome de ferramenta.
            logger.warning("Modelo pediu ferramenta desconhecida: %r", nome)
            return json.dumps(
                {"erro": f"Ferramenta '{nome}' não existe.", "disponiveis": self.nomes()},
                ensure_ascii=False,
            )

        try:
            resultado = tool.execute(**argumentos)
        except ToolError as exc:
            logger.warning("Ferramenta %s falhou: %s", nome, exc)
            return json.dumps({"erro": str(exc)}, ensure_ascii=False)
        except TypeError as exc:
            # Argumento a mais, a menos, ou com nome errado — o modelo inventou
            # a assinatura. Devolver a mensagem ajuda-o a corrigir na próxima.
            logger.warning("Argumentos inválidos para %s (%r): %s", nome, argumentos, exc)
            return json.dumps({"erro": f"Argumentos inválidos para '{nome}'."}, ensure_ascii=False)
        except Exception:  # noqa: BLE001 — nenhuma tool pode derrubar o turno
            logger.exception("Erro inesperado na ferramenta %s", nome)
            return json.dumps(
                {"erro": "Não consegui consultar essa informação agora."},
                ensure_ascii=False,
            )

        return json.dumps(resultado, ensure_ascii=False, default=str)

"""Camada de LLM do chatbot — contrato, implementações e fábrica.

O resto do ClinicOS importa daqui, nunca dos submódulos::

    from apps.chatbot.services.llm import get_llm_client, RespostaLLM

Assim a troca de provedor (Ollama hoje, Anthropic quando a dívida do
``docs/STATUS.md`` for paga) não toca em nenhum import fora deste pacote.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import (
    FragmentoStream,
    LLMClient,
    LLMIndisponivelError,
    RespostaLLM,
    TipoFragmento,
    ToolCall,
)
from .fake import ChamadaLLM, FakeLLMClient, FakeLLMEsgotadoError
from .ollama import OllamaLLMClient

__all__ = [
    "ChamadaLLM",
    "FakeLLMClient",
    "FakeLLMEsgotadoError",
    "FragmentoStream",
    "LLMClient",
    "LLMIndisponivelError",
    "OllamaLLMClient",
    "PROVEDORES",
    "RespostaLLM",
    "TipoFragmento",
    "ToolCall",
    "get_llm_client",
]

# Nome em ``settings.LLM_PROVIDER`` → classe. Registrar aqui (em vez de uma
# cadeia de ``if``) deixa o erro de configuração listar as opções válidas.
PROVEDORES: dict[str, type] = {
    "ollama": OllamaLLMClient,
    "fake": FakeLLMClient,
}


def get_llm_client() -> LLMClient:
    """Instancia o cliente de LLM configurado em ``settings.LLM_PROVIDER``.

    ``fake`` não é só para teste: é o que permite subir a aplicação sem Ollama
    (dev sem GPU, demo offline) e receber uma resposta canned em vez de erro.

    Raises:
        ImproperlyConfigured: provedor desconhecido. Falhar no boot é melhor
            que descobrir no primeiro turno de chat de uma demo.
    """
    nome = str(getattr(settings, "LLM_PROVIDER", "") or "").strip().lower()

    try:
        classe = PROVEDORES[nome]
    except KeyError:
        validos = ", ".join(sorted(PROVEDORES))
        raise ImproperlyConfigured(
            f"LLM_PROVIDER={nome!r} não é um provedor conhecido. Use um de: {validos}."
        ) from None

    return classe()

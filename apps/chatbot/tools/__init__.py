"""Ferramentas que o chatbot pode chamar.

São o único caminho pelo qual dado operacional chega ao modelo — princípio
"chatbot grounded" do ``README.md``. As de leitura vivem em ``consultas.py``; a
única que escreve vive em ``agendamento.py`` `[S5-12]`.

:func:`construir_registry` mora aqui, e não dentro de um dos dois módulos,
porque montar o conjunto do turno deixou de ser assunto de uma das metades.
"""

from __future__ import annotations

import uuid

from .agendamento import CriarLeadEConsultaTool
from .base import BaseTool, ToolError, ToolRegistry
from .consultas import BuscarFaqTool, BuscarSlotsTool, ListarEspecialidadesTool


def construir_registry(conversa_id: uuid.UUID | str | None = None) -> ToolRegistry:
    """Monta o registry de um turno.

    Args:
        conversa_id: Conversa em andamento, repassada à ferramenta de
            agendamento para que ela ache o lead certo `[S5-24]`. É parâmetro
            desta função, e não do ``input_schema`` da tool, porque o modelo não
            conhece esse valor e não pode poder forjá-lo — quem o injeta é a
            view, a partir da sessão. ``None`` é legítimo (teste unitário, shell,
            command): o agendamento segue funcionando e cria um lead sem
            conversa de origem.

    Note:
        Instanciar por turno é requisito, não estilo: o ``enum`` de
        especialidades do ``buscar_slots`` sai do banco, e o ``conversa_id``
        muda a cada conversa. Ver a docstring de :class:`ToolRegistry`.
    """
    return ToolRegistry(
        [
            ListarEspecialidadesTool(),
            BuscarSlotsTool(),
            BuscarFaqTool(),
            CriarLeadEConsultaTool(conversa_id=conversa_id),
        ]
    )


__all__ = [
    "BaseTool",
    "BuscarFaqTool",
    "BuscarSlotsTool",
    "CriarLeadEConsultaTool",
    "ListarEspecialidadesTool",
    "ToolError",
    "ToolRegistry",
    "construir_registry",
]

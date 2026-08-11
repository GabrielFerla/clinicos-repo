"""Ferramentas que o chatbot pode chamar.

São o único caminho pelo qual dado operacional chega ao modelo — princípio
"chatbot grounded" do ``README.md``.
"""

from .base import BaseTool, ToolError, ToolRegistry
from .consultas import (
    BuscarFaqTool,
    BuscarSlotsTool,
    ListarEspecialidadesTool,
    construir_registry,
)

__all__ = [
    "BaseTool",
    "BuscarFaqTool",
    "BuscarSlotsTool",
    "ListarEspecialidadesTool",
    "ToolError",
    "ToolRegistry",
    "construir_registry",
]

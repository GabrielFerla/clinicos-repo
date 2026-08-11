"""Admin do app ``chatbot``.

Duas telas com propósitos opostos:

* ``FaqVector`` é **curadoria** — editável, e é onde o conteúdo que fundamenta
  as respostas do bot é mantido.
* ``InteracaoChat`` é **auditoria** — somente leitura. Quem escreve é o
  ``ChatService``; um turno editável pela mão humana destruiria o valor
  probatório do log de alucinação `[S5-26]`.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import FaqVector, InteracaoChat


@admin.register(FaqVector)
class FaqVectorAdmin(admin.ModelAdmin):
    """Base de conhecimento consultada por ``buscar_faq``.

    Os campos ``embedding_*`` e ``conteudo_hash`` são somente leitura: quem os
    escreve é o comando de reindexação. Editar à mão faria a linha alegar um
    vetor que a coluna ``EMBEDDING`` não tem — e a busca semântica devolveria
    ranking sem significado, sem erro nenhum.
    """

    list_display = ("pergunta", "categoria", "ativo", "indexado", "atualizado_em")
    list_filter = ("ativo", "categoria", "embedding_modelo")
    # ``resposta`` fica fora da busca de propósito: no Oracle é NCLOB, e a
    # regra do projeto é não usar NCLOB em ``WHERE``/``ORDER BY``.
    search_fields = ("pergunta", "categoria")
    ordering = ("categoria", "pergunta")
    readonly_fields = (
        "criado_em",
        "atualizado_em",
        "embedding_gerado_em",
        "embedding_modelo",
        "embedding_dim",
        "conteudo_hash",
    )
    fieldsets = (
        (None, {"fields": ("pergunta", "resposta", "categoria", "ativo")}),
        (
            "Indexação vetorial",
            {
                "fields": (
                    "embedding_gerado_em",
                    "embedding_modelo",
                    "embedding_dim",
                    "conteudo_hash",
                ),
                "description": (
                    "Preenchido pelo comando de reindexação. A coluna EMBEDDING "
                    "não passa pelo ORM — ver docs/CHAT_MVP.md, Bloco 1B."
                ),
            },
        ),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em")}),
    )

    @admin.display(description="indexada", boolean=True, ordering="embedding_gerado_em")
    def indexado(self, obj: FaqVector) -> bool:
        """Mostra de relance quais FAQs o chatbot consegue de fato encontrar."""
        return obj.embedding_gerado_em is not None


@admin.register(InteracaoChat)
class InteracaoChatAdmin(admin.ModelAdmin):
    """Log de turnos do chat — **somente leitura**.

    As três permissões negadas cobrem tanto a UI quanto as ações em massa; e
    ``readonly_fields`` cobrindo tudo garante que nem a tela de detalhe ofereça
    um campo editável.
    """

    list_display = (
        "criado_em",
        "conversa_id",
        "sequencia",
        "modelo",
        "latencia_ms",
        "alucinacao_detectada",
        "tem_erro",
    )
    list_filter = ("alucinacao_detectada", "modelo", "criado_em")
    # ``pergunta``, ``resposta`` e ``erro`` são TextField (NCLOB no Oracle) e
    # ficam fora da busca pelo mesmo motivo do ``FaqVectorAdmin``.
    search_fields = ("conversa_id", "modelo")
    date_hierarchy = "criado_em"
    ordering = ("-criado_em",)

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        """Todos os campos concretos, sempre — a tabela é auditoria."""
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    @admin.display(description="erro", boolean=True)
    def tem_erro(self, obj: InteracaoChat) -> bool:
        return bool(obj.erro)

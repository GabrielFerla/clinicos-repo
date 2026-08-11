"""Admin do app ``agenda``.

O Admin é a UI de operação da agenda no MVP1 (ADR-0005): é aqui que a
recepção bloqueia horário e confere disponibilidade enquanto a geração
automática de slots (Sprint 3) não existe.
"""

from __future__ import annotations

from django.contrib import admin

from .models import AgendaSlot


@admin.register(AgendaSlot)
class AgendaSlotAdmin(admin.ModelAdmin):
    """Slots de atendimento.

    ``list_select_related`` importa: o ``__str__`` do slot lê ``medico.nome``,
    e sem isso a listagem faria uma query por linha.
    """

    list_display = ("data", "hora_inicio", "hora_fim", "medico", "status")
    list_filter = ("status", "data", "medico")
    search_fields = ("medico__nome", "medico__crm_numero")
    list_select_related = ("medico",)
    autocomplete_fields = ("medico",)
    date_hierarchy = "data"
    ordering = ("data", "hora_inicio")
    readonly_fields = ("criado_em",)

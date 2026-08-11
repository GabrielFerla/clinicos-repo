"""Admin do app ``crm``.

O Django Admin é a UI do CRM no MVP1 (ADR-0005): não há tela custom para
cadastrar especialidade ou médico, então o que estiver configurado aqui é
literalmente o produto que a recepção usa.
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from .models import Especialidade, Medico, MedicoEspecialidade


class MedicoEspecialidadeInline(admin.TabularInline):
    """Vínculos de especialidade editados dentro da ficha do médico.

    Inline em vez de tela separada porque ninguém cadastra um vínculo sem
    estar olhando para o médico — e o ``through`` model impede o widget M2M
    padrão de aparecer sozinho.
    """

    model = MedicoEspecialidade
    extra = 1
    autocomplete_fields = ("especialidade",)


@admin.register(Especialidade)
class EspecialidadeAdmin(admin.ModelAdmin):
    """Catálogo de subespecialidades oftalmológicas."""

    list_display = ("nome", "slug", "ativo", "total_medicos", "criado_em")
    list_filter = ("ativo",)
    # ``descricao`` é CharField (não NCLOB), então entra na busca sem risco.
    search_fields = ("nome", "slug", "descricao")
    prepopulated_fields = {"slug": ("nome",)}
    ordering = ("nome",)
    readonly_fields = ("criado_em",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Especialidade]:
        """Anota a contagem de médicos — evita um ``COUNT`` por linha da listagem."""
        return super().get_queryset(request).annotate(_total_medicos=Count("medicos"))

    @admin.display(description="médicos", ordering="_total_medicos")
    def total_medicos(self, obj: Especialidade) -> int:
        return obj._total_medicos


@admin.register(Medico)
class MedicoAdmin(admin.ModelAdmin):
    """Corpo clínico. ``search_fields`` é pré-requisito do ``autocomplete_fields``
    usado pelo admin da agenda."""

    list_display = ("nome", "crm_completo", "rqe", "ativo", "criado_em")
    list_filter = ("ativo", "crm_uf", "especialidades")
    search_fields = ("nome", "crm_numero", "rqe")
    ordering = ("nome",)
    readonly_fields = ("criado_em",)
    inlines = (MedicoEspecialidadeInline,)

    @admin.display(description="CRM", ordering="crm_numero")
    def crm_completo(self, obj: Medico) -> str:
        return obj.crm_completo


@admin.register(MedicoEspecialidade)
class MedicoEspecialidadeAdmin(admin.ModelAdmin):
    """Vínculo médico ↔ especialidade.

    Registrado além do inline para permitir a leitura inversa ("quem atende
    retina?") sem passar por cada ficha de médico.
    """

    list_display = ("medico", "especialidade", "principal")
    list_filter = ("principal", "especialidade")
    search_fields = ("medico__nome", "medico__crm_numero", "especialidade__nome")
    list_select_related = ("medico", "especialidade")
    autocomplete_fields = ("medico", "especialidade")

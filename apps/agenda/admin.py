"""Admin do app ``agenda``.

O Admin é a UI de operação da agenda no MVP1 (ADR-0005): é aqui que a
recepção bloqueia horário, cadastra as regras semanais que geram os slots e
confere as consultas marcadas `[S3-10]`.

As três telas cobrem as três camadas do domínio, na ordem em que a informação
flui: ``AgendaRegra`` (o molde recorrente) → ``AgendaSlot`` (a janela concreta
gerada a partir dela) → ``Consulta`` (a ocupação da janela por um paciente).
"""

from __future__ import annotations

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest

from .models import AgendaRegra, AgendaSlot, Consulta


@admin.register(AgendaRegra)
class AgendaRegraAdmin(admin.ModelAdmin):
    """Regras semanais de disponibilidade — o molde dos slots `[S3-10]`.

    ``autocomplete_fields`` no médico depende de ``MedicoAdmin.search_fields``,
    que já existe; sem ele o formulário renderiza um ``<select>`` com o corpo
    clínico inteiro.

    ``dia_semana`` entra na listagem como campo, e não via
    ``get_dia_semana_display``: o Admin já troca o número pelo rótulo de
    ``choices`` sozinho, e assim a coluna continua ordenável pelo banco.
    """

    list_display = (
        "medico",
        "dia_semana",
        "hora_inicio",
        "hora_fim",
        "duracao_consulta_min",
        "intervalo_min",
        "vigencia",
        "ativo",
    )
    list_filter = ("ativo", "dia_semana", "medico")
    search_fields = ("medico__nome", "medico__crm_numero")
    list_select_related = ("medico",)  # ``__str__`` da regra lê ``medico.nome``
    autocomplete_fields = ("medico",)
    ordering = ("medico", "dia_semana", "hora_inicio")
    list_per_page = 50
    readonly_fields = ("criado_em",)
    fieldsets = (
        (None, {"fields": ("medico", "dia_semana", "hora_inicio", "hora_fim")}),
        (
            "Slots gerados",
            {
                "fields": ("duracao_consulta_min", "intervalo_min"),
                "description": (
                    "Duração de cada consulta e a folga entre uma e a próxima, em minutos. "
                    "É o que o comando de geração de slots usa para fatiar a janela."
                ),
            },
        ),
        (
            "Vigência",
            {
                "fields": ("vigencia_inicio", "vigencia_fim", "ativo"),
                "description": (
                    "Para mudar uma regra que já vale, preencha o fim da vigência desta e "
                    "crie outra começando no dia seguinte — assim os slots já gerados "
                    "mantêm a procedência."
                ),
            },
        ),
        ("Auditoria", {"fields": ("criado_em",), "classes": ("collapse",)}),
    )

    @admin.display(description="vigência", ordering="vigencia_inicio")
    def vigencia(self, obj: AgendaRegra) -> str:
        """Janela de validade em uma coluna só, ordenável pelo início."""
        if obj.vigencia_fim is None:
            return f"desde {obj.vigencia_inicio:%d/%m/%Y}"
        return f"{obj.vigencia_inicio:%d/%m/%Y} – {obj.vigencia_fim:%d/%m/%Y}"


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


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    """Consultas marcadas `[S3-10]`.

    ``list_select_related`` não é otimização opcional aqui: o ``__str__`` da
    consulta lê ``paciente.nome`` **e** ``slot.data``, e as colunas de data e
    hora saem do slot. Sem ele, cada linha da listagem dispara três queries —
    o N+1 clássico, invisível em base de teste e óbvio em produção.

    A tela é editável de propósito (a recepção remarca e cancela por aqui),
    mas ``medico`` fica somente-leitura: ele é cópia de ``slot.medico``, e
    escolhê-lo à mão criaria uma consulta cujo médico não é o dono do horário —
    exatamente a invariante que o model diz caber a quem escreve manter (ver
    ``Consulta.medico``). Quem o preenche aqui é :meth:`save_model`.
    """

    list_display = (
        "paciente",
        "medico",
        "data_do_slot",
        "hora_do_slot",
        "status",
        "origem",
        "criado_em",
    )
    list_filter = ("status", "origem", "medico")
    search_fields = ("paciente__nome", "medico__nome")
    list_select_related = ("paciente", "medico", "slot")
    autocomplete_fields = ("paciente", "slot")
    ordering = ("-id",)
    list_per_page = 50
    readonly_fields = ("medico", "criado_em", "atualizado_em")
    fieldsets = (
        (None, {"fields": ("paciente", "slot", "medico")}),
        ("Atendimento", {"fields": ("status", "origem", "observacoes")}),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    def save_model(
        self, request: HttpRequest, obj: Consulta, form: ModelForm, change: bool
    ) -> None:
        """Deriva ``medico`` do slot antes de gravar.

        O campo não está no formulário (é ``readonly``), então sem isto o
        ``INSERT`` iria sem médico e morreria na constraint ``NOT NULL``.
        Derivar em vez de perguntar é o que garante a invariante
        ``consulta.medico == slot.medico`` na única tela que escreve consulta à
        mão.
        """
        obj.medico = obj.slot.medico
        super().save_model(request, obj, form, change)

    @admin.display(description="data", ordering="slot__data")
    def data_do_slot(self, obj: Consulta) -> str:
        return f"{obj.slot.data:%d/%m/%Y}"

    @admin.display(description="hora", ordering="slot__hora_inicio")
    def hora_do_slot(self, obj: Consulta) -> str:
        return f"{obj.slot.hora_inicio:%H:%M}"

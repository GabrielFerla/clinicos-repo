"""Admin do app ``agenda``.

O Admin é a UI de operação da agenda no MVP1 (ADR-0005): é aqui que a
recepção bloqueia horário, cadastra as regras semanais que geram os slots e
confere as consultas marcadas `[S3-10]`.

As três telas cobrem as três camadas do domínio, na ordem em que a informação
flui: ``AgendaRegra`` (o molde recorrente) → ``AgendaSlot`` (a janela concreta
gerada a partir dela) → ``Consulta`` (a ocupação da janela por um paciente).

``ConsultaAdmin`` é a única das três que **escreve pelo service** `[S3-7]`: ver
a docstring da classe.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils import timezone

from .models import AgendaRegra, AgendaSlot, Consulta
from .services.agendamento import (
    MSG_INDISPONIVEL,
    MSG_PASSADO,
    AgendamentoService,
    SlotIndisponivelError,
)


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


class ConsultaAdminForm(forms.ModelForm):
    """Formulário de consulta com a checagem de disponibilidade do slot `[S3-7]`.

    Existe para que "esse horário já foi tomado" chegue à recepção como **erro
    de campo**, e não como exceção subindo de :meth:`ConsultaAdmin.save_model`.
    A validação repete de propósito o que ``AgendamentoService.agendar`` já
    verifica — as duas camadas respondem a perguntas diferentes:

    * aqui é *usabilidade*: o erro aparece grudado no campo ``slot``, com o
      resto do formulário preservado;
    * lá é *correção*: o service relê a linha sob ``SELECT ... FOR UPDATE``,
      dentro da transação, e é o único lugar que pode afirmar algo sobre o
      estado do slot no instante do ``INSERT``.

    Entre esta validação e aquele ``INSERT`` cabe uma corrida (alguém marca o
    mesmo horário no meio do caminho). Ela é rara e está coberta —
    ver :meth:`ConsultaAdmin.changeform_view`.

    A checagem só roda na **criação**: numa edição o slot já está
    ``RESERVADO`` — por esta própria consulta —, e validá-lo recusaria toda
    troca de status ou observação.
    """

    class Meta:
        model = Consulta
        # Lista explícita (e sem ``medico``, que é derivado de ``slot.medico`` e
        # nunca editável). Quem realmente decide os campos deste formulário é o
        # ``ModelAdmin``, que os recalcula a partir de ``fieldsets`` menos
        # ``readonly_fields`` — esta Meta só vale se alguém instanciar a classe
        # fora do Admin.
        fields = ("paciente", "slot", "status", "origem", "observacoes")

    def clean_slot(self) -> AgendaSlot | None:
        slot: AgendaSlot | None = self.cleaned_data.get("slot")
        if slot is None or self.instance.pk is not None:
            return slot
        if slot.status != AgendaSlot.Status.LIVRE:
            raise forms.ValidationError(MSG_INDISPONIVEL)
        if slot.data < timezone.localdate():
            raise forms.ValidationError(MSG_PASSADO)
        return slot


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
    ``Consulta.medico``).

    Criar aqui passa pelo ``AgendamentoService`` `[S3-7]`
    ----------------------------------------------------
    Até a S2-10 esta tela criava ``Consulta`` direto pelo ORM. Não havia
    overbooking — o ``OneToOneField`` de ``Consulta.slot`` recusa a segunda
    consulta no mesmo slot —, mas o **slot continuava ``LIVRE``**: a tool
    ``buscar_slots`` do chatbot seguia oferecendo aquele horário, e o paciente
    só descobria o problema ao tentar fechar. Marcar o slot é responsabilidade
    do service, e :meth:`save_model` roteia a criação por ele.

    A **edição** não passa pelo service, e não deve: mudar status ou observação
    de uma consulta existente não toca em disponibilidade, e ``agendar()`` só
    sabe criar.
    """

    form = ConsultaAdminForm
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

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        """Na criação, ``status`` e ``origem`` também são somente-leitura.

        Quem os define é o ``AgendamentoService``: ele nasce ``AGENDADA`` e, por
        esta tela, ``RECEPCAO``. Deixá-los editáveis no formulário de adição
        seria oferecer uma escolha que o ``save_model`` descarta em silêncio —
        e um dropdown de ``origem`` na recepção contaminaria o denominador da
        métrica de conversão do chatbot `[S5-28]`. Na edição voltam a ser
        editáveis: é assim que a recepção confirma, cancela e marca falta.
        """
        if obj is None:
            return (*self.readonly_fields, "status", "origem")
        return self.readonly_fields

    def save_model(
        self, request: HttpRequest, obj: Consulta, form: forms.ModelForm, change: bool
    ) -> None:
        """Roteia a **criação** pelo ``AgendamentoService``; edição segue pelo ORM.

        Na edição, ainda derivamos ``medico`` do slot: o campo não está no
        formulário (é ``readonly``), então sem isto uma remarcação gravaria o
        médico antigo — quebrando a invariante ``consulta.medico ==
        slot.medico``.

        Na criação, ``agendar()`` faz as três coisas que o ``obj.save()`` não
        fazia: relê o slot sob lock, preenche ``medico`` a partir dele e marca o
        slot como ``RESERVADO``. Ele devolve uma instância **nova**, então
        copiamos o estado persistido de volta para ``obj`` — o Admin continua
        usando esse objeto depois daqui (``log_addition``, a mensagem de sucesso
        e o link para o registro criado), e um ``obj`` sem ``pk`` estouraria ali.
        """
        if change:
            obj.medico = obj.slot.medico
            super().save_model(request, obj, form, change)
            return

        consulta = AgendamentoService.agendar(
            paciente=obj.paciente,
            # O id, e não a instância: o service relê a linha sob lock, e é essa
            # releitura que impede o agendamento sobre um objeto defasado.
            slot_id=obj.slot_id,
            # Consulta nascida nesta tela veio da recepção, por definição.
            # ``agendar()`` não aceita default para ``origem`` de propósito.
            origem=Consulta.Origem.RECEPCAO,
            observacoes=obj.observacoes,
        )
        for campo in obj._meta.concrete_fields:
            setattr(obj, campo.attname, getattr(consulta, campo.attname))

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Rede de segurança para a corrida que ``ConsultaAdminForm`` não pega.

        ``clean_slot`` valida a disponibilidade **antes** do ``INSERT``; se
        outra pessoa (ou o chatbot) tomar o horário nesse intervalo, quem
        recusa é o service, já dentro de :meth:`save_model` — tarde demais para
        virar erro de campo, porque o Admin só valida o formulário antes de
        chamá-lo.

        Sem este ``except``, essa corrida é um **erro 500** na cara da recepção.
        Com ele, é uma mensagem em vermelho e o formulário de novo. O
        ``changeform_view`` do Django roda dentro de um ``transaction.atomic``,
        então quando a exceção chega aqui a transação já foi desfeita — nenhuma
        consulta meio-criada sobrevive.

        Só ``SlotIndisponivelError`` é capturado (``SlotNoPassadoError`` é
        subclasse dela, e traz a própria mensagem). Qualquer outra exceção
        continua subindo: engolir erro desconhecido em tela de agendamento
        esconderia o bug em vez de corrigi-lo.
        """
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except SlotIndisponivelError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(request.get_full_path())

    @admin.display(description="data", ordering="slot__data")
    def data_do_slot(self, obj: Consulta) -> str:
        return f"{obj.slot.data:%d/%m/%Y}"

    @admin.display(description="hora", ordering="slot__hora_inicio")
    def hora_do_slot(self, obj: Consulta) -> str:
        return f"{obj.slot.hora_inicio:%H:%M}"

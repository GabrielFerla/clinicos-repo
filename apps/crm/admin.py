"""Admin do app ``crm``.

O Django Admin é a UI do CRM no MVP1 (ADR-0005): não há tela custom para
cadastrar especialidade ou médico, então o que estiver configurado aqui é
literalmente o produto que a recepção usa.

Duas telas concentram a complexidade deste módulo:

* ``Paciente`` `[S2-9]` — o CPF não existe em claro no model, então o Admin
  precisa de um formulário próprio para receber, validar e gravar o número
  pelo único caminho permitido (``Paciente.definir_cpf``). Ver
  :class:`PacienteAdminForm`.
* ``Lead`` `[S5-23]` — o funil do CRM, com a etapa editável direto na
  listagem para que mover um lead não custe dois cliques e um reload.
"""

from __future__ import annotations

import re

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from apps.agenda.models import Consulta
from apps.core.admin import RestritoAoMedicoMixin
from apps.core.security.hash import normalize_cpf, validar_cpf

from .models import Especialidade, Lead, Medico, MedicoEspecialidade, Paciente

# Usado para decidir se o termo digitado na busca é um CPF (ver
# ``PacienteAdmin.get_search_results``).
_SO_DIGITOS = re.compile(r"\D+")


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
    usado pelo admin da agenda.

    ``usuario`` é o vínculo de que a permissão por perfil `[S2-10]` depende:
    preenchê-lo é o que faz o médico enxergar apenas os próprios pacientes,
    consultas e prontuários. Entra por ``raw_id_fields``, e não por
    ``autocomplete_fields``: o autocomplete exigiria ``search_fields`` em
    ``UsuarioAdmin`` **e** publicaria, na busca, a lista de logins da clínica
    para qualquer um com acesso a esta tela. O ``raw_id`` abre a listagem de
    usuários em popup, que já respeita as permissões do próprio
    ``UsuarioAdmin``.
    """

    list_display = ("nome", "crm_completo", "rqe", "usuario", "ativo", "criado_em")
    list_filter = ("ativo", "crm_uf", "especialidades")
    search_fields = ("nome", "crm_numero", "rqe")
    list_select_related = ("usuario",)  # a coluna ``usuario`` lê o ``__str__`` dele
    raw_id_fields = ("usuario",)
    ordering = ("nome",)
    readonly_fields = ("criado_em",)
    inlines = (MedicoEspecialidadeInline,)
    fieldsets = (
        (None, {"fields": ("nome", "crm_numero", "crm_uf", "rqe", "ativo")}),
        (
            "Acesso ao painel",
            {
                "fields": ("usuario",),
                "description": (
                    "Vincule o login deste médico para que ele veja apenas os próprios "
                    "pacientes, consultas e prontuários. Sem vínculo, um usuário de perfil "
                    "“Médico” não enxerga nada — o padrão é o fechado."
                ),
            },
        ),
        ("Auditoria", {"fields": ("criado_em",), "classes": ("collapse",)}),
    )

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


class PacienteAdminForm(forms.ModelForm):
    """Formulário de cadastro de paciente com CPF de entrada `[S2-9]`.

    ``Paciente`` não tem campo ``cpf``: o número vive cifrado em
    ``cpf_cifrado`` e hasheado em ``cpf_hash``, e o único caminho de escrita é
    ``Paciente.definir_cpf`` (ver a docstring do model). Um ``ModelForm`` puro,
    portanto, não teria onde a recepção digitar o CPF — daí este campo
    **não-model**, que existe só para a viagem "tela → ``definir_cpf``".

    O que ele **não** faz é igualmente importante: em nenhum ponto atribui
    ``cpf_cifrado`` ou ``cpf_hash`` diretamente. Preencher uma sem a outra, ou
    preenchê-las a partir de valores diferentes, produz um paciente cujo hash
    de busca aponta para um CPF e cujo ciphertext guarda outro — um bug
    silencioso e irreparável depois do INSERT.

    Na edição o campo nasce vazio e **em branco significa "manter o CPF
    atual"**. A alternativa — pré-preencher com o número decifrado — poria os
    11 dígitos no HTML de toda tela de edição, incluindo as abertas por engano.
    """

    cpf = forms.CharField(
        label="CPF",
        max_length=14,  # 11 dígitos + os 3 separadores da máscara
        required=False,  # a obrigatoriedade real é decidida no __init__
        help_text="Com ou sem pontuação. Validado pelos dois dígitos verificadores.",
    )

    class Meta:
        model = Paciente
        fields = ("nome", "data_nascimento", "email", "telefone", "ativo")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        criando = self.instance.pk is None
        # Obrigatório só na criação: paciente sem CPF não é identificável, mas
        # exigir a redigitação a cada edição de telefone seria pedir para o CPF
        # circular por telas que não precisam dele.
        self.fields["cpf"].required = criando
        if not criando:
            self.fields["cpf"].help_text = (
                f"CPF atual: {self.instance.cpf_mascarado}. "
                "Deixe em branco para manter; preencha apenas para corrigir."
            )

    def clean_cpf(self) -> str:
        """Normaliza, valida os verificadores e recusa CPF já cadastrado.

        A checagem de duplicidade acontece aqui, e não no banco, porque a
        ``UniqueConstraint`` é sobre ``cpf_hash`` — coluna que não está no
        formulário. Sem esta validação o cadastro duplicado só falharia no
        ``INSERT``, com um ``IntegrityError`` que vira erro 500 em vez de
        mensagem de campo.

        Returns:
            Os 11 dígitos normalizados, ou ``""`` quando a edição optou por
            manter o CPF atual.
        """
        bruto = (self.cleaned_data.get("cpf") or "").strip()
        if not bruto:
            # ``required`` já barrou o caso de criação; aqui só chega edição.
            return ""

        try:
            digitos = normalize_cpf(bruto)
        except (TypeError, ValueError) as exc:
            raise ValidationError("O CPF precisa ter 11 dígitos.") from exc

        if not validar_cpf(digitos):
            raise ValidationError(
                "CPF inválido: os dígitos verificadores não conferem. Confira o número digitado."
            )

        duplicado = Paciente.objects.buscar_por_cpf(digitos).exclude(pk=self.instance.pk).first()
        if duplicado is not None:
            raise ValidationError(
                f"Este CPF já está cadastrado para o paciente {duplicado.nome} "
                f"(código {duplicado.pk}). Edite o cadastro existente em vez de criar outro."
            )
        return digitos

    def save(self, commit: bool = True) -> Paciente:
        """Grava o CPF pelo único caminho permitido, quando houver CPF novo.

        ``definir_cpf`` é chamado com ``commit=False`` também, porque o
        ``ModelAdmin`` salva em duas etapas (``save_form`` devolve a instância
        sem persistir e ``save_model`` chama ``obj.save()``) — a cifragem tem
        que estar na instância antes desse segundo passo.
        """
        paciente: Paciente = super().save(commit=False)
        cpf = self.cleaned_data.get("cpf")
        if cpf:
            paciente.definir_cpf(cpf)
        if commit:
            paciente.save()
            self.save_m2m()
        return paciente


@admin.register(Paciente)
class PacienteAdmin(RestritoAoMedicoMixin, admin.ModelAdmin):
    """Cadastro de pacientes `[S2-9]` — titular de dado pessoal sensível (LGPD).

    Três regras atravessam toda a configuração desta classe:

    1. **O CPF em claro não aparece em listagem.** A coluna mostra
       ``cpf_mascarado``; os 11 dígitos só existem na tela de detalhe, e ainda
       assim apenas para quem digitá-los.
    2. **Nada de ``cpf_cifrado``/``cpf_hash`` editáveis.** Eles ficam fora dos
       fieldsets *e* em ``readonly_fields`` — o segundo cinto existe para o dia
       em que alguém acrescentar a coluna a um fieldset sem ler esta docstring.
    3. **Médico vê só os pacientes dele** `[S2-10]`, via
       :class:`~apps.core.admin.RestritoAoMedicoMixin`.

    A restrição atinge, de graça, um caminho que passa despercebido: o
    ``autocomplete`` de paciente usado por ``ConsultaAdmin`` e
    ``ProntuarioAdmin`` responde a partir deste ``get_queryset``. Sem o mixin,
    um médico digitando três letras na tela de consulta receberia nomes de
    pacientes que não são dele — vazamento por caminho lateral, com o
    ``changelist`` aparentemente protegido.
    """

    form = PacienteAdminForm
    list_display = ("nome", "cpf_mascarado", "data_nascimento", "telefone", "email", "ativo")
    list_filter = ("ativo",)
    # ``cpf_hash`` **não** entra aqui: quem busca digita o CPF, não o hash — a
    # tradução de um para o outro é feita em ``get_search_results``.
    search_fields = ("nome", "email")
    ordering = ("nome",)
    list_per_page = 50
    readonly_fields = ("cpf_cifrado", "cpf_hash", "criado_em", "atualizado_em")
    fieldsets = (
        (None, {"fields": ("nome", "cpf", "data_nascimento")}),
        ("Contato", {"fields": ("email", "telefone")}),
        (
            "Situação",
            {
                "fields": ("ativo",),
                "description": (
                    "Paciente nunca é apagado — a retenção do prontuário é de 20 anos (CFM). "
                    "Desmarque “ativo” para arquivar."
                ),
            },
        ),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    def restringir_ao_medico(
        self, queryset: QuerySet[Paciente], medico: Medico
    ) -> QuerySet[Paciente]:
        """Pacientes com ao menos uma consulta com este médico.

        Subquery (``pk__in``) em vez de ``filter(consultas__medico=...)``: o
        join traria o paciente uma vez por consulta e obrigaria a um
        ``.distinct()``, que num changelist paginado é ``SELECT DISTINCT`` sobre
        todas as colunas da tela. A subquery devolve cada paciente uma vez, sem
        alterar as colunas do ``SELECT`` externo.

        Não há filtro por ``status``: uma consulta cancelada ou uma falta
        também são atendimento desse médico, e o histórico é o que ele precisa
        enxergar.
        """
        return queryset.filter(pk__in=Consulta.objects.filter(medico=medico).values("paciente_id"))

    @admin.display(description="CPF")
    def cpf_mascarado(self, obj: Paciente) -> str:
        """Coluna da listagem. Não é ordenável de propósito: ordenar por CPF
        exigiria decifrar a tabela inteira."""
        return obj.cpf_mascarado

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Paciente], search_term: str
    ) -> tuple[QuerySet[Paciente], bool]:
        """Busca por CPF via hash determinístico; qualquer outro termo cai no padrão.

        É o requisito da S2-9 ("busca por CPF via hash determinístico") e da
        demo da sprint: a recepção digita o CPF que o paciente informou ao
        telefone e o sistema o encontra, mesmo o número estando cifrado. Um
        ``icontains`` sobre ``cpf_cifrado`` não acharia nada — cada linha tem
        nonce próprio, então o mesmo CPF gera ciphertexts diferentes.

        O gatilho é ter exatamente 11 dígitos após remover a pontuação, o que
        distingue CPF de "1234" (busca por nome) sem exigir um campo separado
        na tela. Fora desse caso, delega para ``super()``, que varre
        ``search_fields``.
        """
        digitos = _SO_DIGITOS.sub("", search_term or "")
        if len(digitos) == 11:
            alvo = Paciente.objects.buscar_por_cpf(digitos).values("pk")
            # Filtra o queryset recebido (que já pode vir restrito por
            # ``list_filter``) em vez de devolver o do manager.
            return queryset.filter(pk__in=alvo), False
        return super().get_search_results(request, queryset, search_term)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    """Funil de leads do chatbot `[S5-23]`.

    ``list_editable`` na etapa é a feature, não um detalhe: mover um lead de
    "qualificado" para "agendado" é a operação mais repetida desta tela, e sem
    isso custaria abrir o detalhe, salvar e voltar. O model aceita pulo de
    etapa e retrocesso de propósito (ver a docstring de ``Lead``), então o
    dropdown na listagem não precisa de nenhuma trava.
    """

    list_display = (
        "nome",
        "etapa",
        "especialidade_interesse",
        "telefone",
        "email",
        "consulta",
        "criado_em",
    )
    list_editable = ("etapa",)
    list_filter = ("etapa", "especialidade_interesse", "criado_em")
    search_fields = ("nome", "email", "telefone")
    # Caminhos aninhados porque ``Consulta.__str__`` lê ``paciente.nome`` e
    # ``slot.data``: sem eles a coluna ``consulta`` faria três queries por linha.
    list_select_related = ("especialidade_interesse", "consulta__paciente", "consulta__slot")
    autocomplete_fields = ("especialidade_interesse", "consulta")
    date_hierarchy = "criado_em"
    ordering = ("-id",)
    list_per_page = 50
    readonly_fields = ("criado_em", "atualizado_em")
    fieldsets = (
        (None, {"fields": ("nome", "etapa", "especialidade_interesse")}),
        ("Contato", {"fields": ("email", "telefone")}),
        (
            "Origem e conversão",
            {
                "fields": ("conversa_id", "consulta"),
                "description": (
                    "“Conversa” é o UUID do diálogo no chatbot que originou o lead; "
                    "fica vazio quando a recepção cadastrou à mão."
                ),
            },
        ),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

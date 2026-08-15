"""Admin do app ``prontuario``.

Três telas com três regimes de escrita, herdados diretamente dos models:

* ``Prontuario`` é **editável** — na prática só se cria, já que o agregador não
  carrega nada além do vínculo com o paciente.
* ``Evolucao`` é **somente leitura**, e aqui isso não é preferência de UX: o
  trigger PL/SQL ``TRG_EVOLUCAO_IMUTAVEL`` `[S1-10]` recusa todo ``UPDATE`` e
  ``DELETE`` com ``ORA-20001``. Uma tela editável não corromperia o prontuário
  — ela produziria erro 500 na cara da recepção. A retificação tem caminho
  próprio: nova evolução apontando para a anterior.
* ``LogAcesso`` é **somente leitura** pelo motivo clássico da auditoria: log
  que se edita não audita nada. Quem escreve nele é o middleware LGPD da
  Sprint 6, nunca a mão humana.

As duas telas somente-leitura seguem o mesmo molde do ``InteracaoChatAdmin``
(``apps/chatbot/admin.py``): as três permissões negadas cobrem a UI e as ações
em massa, e ``get_readonly_fields`` devolvendo todos os campos concretos
garante que nem a tela de detalhe ofereça um campo editável.

Nenhum ``TextField`` entra em ``search_fields`` — no Oracle vira ``NCLOB``, que
não pode aparecer em ``WHERE``/``ORDER BY``. É o caso de ``Evolucao.texto``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from apps.agenda.models import Consulta
from apps.core.admin import RestritoAoMedicoMixin

from .models import Evolucao, LogAcesso, Prontuario

if TYPE_CHECKING:
    from apps.crm.models import Medico


@admin.register(Prontuario)
class ProntuarioAdmin(RestritoAoMedicoMixin, admin.ModelAdmin):
    """Agregador clínico — uma linha por paciente.

    ``autocomplete_fields`` no paciente não é só conforto: o ``<select>``
    padrão renderizaria a base inteira de pacientes numa página, e o rótulo de
    cada opção sai do ``__str__``, o que na prática publicaria a lista completa
    de nomes atendidos pela clínica em qualquer tela de criação.

    O recorte por perfil `[S2-10]` é o mais consequente dos três: prontuário é
    dado clínico, e "médico vê só os seus" aqui é a regra que a LGPD e o
    sigilo profissional cobram. Ver
    :class:`~apps.core.admin.RestritoAoMedicoMixin`.
    """

    list_display = ("paciente", "total_evolucoes", "criado_em")
    search_fields = ("paciente__nome",)
    list_select_related = ("paciente",)  # ``__str__`` lê ``paciente.nome``
    autocomplete_fields = ("paciente",)
    ordering = ("-id",)
    list_per_page = 50
    readonly_fields = ("criado_em",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Prontuario]:
        """Anota a contagem de evoluções — evita um ``COUNT`` por linha da listagem.

        O ``super()`` é o do mixin (ver a ordem de bases da classe), então a
        anotação se aplica **sobre** o queryset já recortado por perfil. Inverter
        a ordem das bases faria a anotação vir de um queryset irrestrito.
        """
        return super().get_queryset(request).annotate(_total_evolucoes=Count("evolucoes"))

    def restringir_ao_medico(
        self, queryset: QuerySet[Prontuario], medico: Medico
    ) -> QuerySet[Prontuario]:
        """Prontuários dos pacientes que têm consulta com este médico.

        O recorte é por **paciente**, e não por autoria de evolução
        (``evolucoes__medico``): um médico que vai atender amanhã precisa ler o
        histórico de antes de existir registro dele ali. Autoria responde outra
        pergunta — "o que eu escrevi" —, que o filtro por médico de
        ``EvolucaoAdmin`` já cobre.

        Mesma subquery de ``PacienteAdmin.restringir_ao_medico``, pelo mesmo
        motivo: evita o ``DISTINCT`` que o join traria.
        """
        return queryset.filter(
            paciente_id__in=Consulta.objects.filter(medico=medico).values("paciente_id")
        )

    @admin.display(description="evoluções", ordering="_total_evolucoes")
    def total_evolucoes(self, obj: Prontuario) -> int:
        return obj._total_evolucoes


@admin.register(Evolucao)
class EvolucaoAdmin(admin.ModelAdmin):
    """Registro clínico — **somente leitura** (append-only garantido no banco).

    Ver a docstring do módulo: a proibição vem do trigger, não daqui. O que
    esta classe faz é impedir que a tela ofereça uma operação que o banco vai
    recusar.
    """

    list_display = ("criado_em", "prontuario", "medico", "consulta", "corrige")
    list_filter = ("medico", "criado_em")
    # ``texto`` fica fora da busca: é o único ``TextField`` do módulo (NCLOB no
    # Oracle). Quem procura conteúdo clínico chega pelo paciente ou pelo autor.
    search_fields = ("prontuario__paciente__nome", "medico__nome")
    # Cada coluna acima atravessa uma FK cujo ``__str__`` lê o objeto seguinte
    # (``Prontuario`` → paciente, ``Consulta`` → paciente e slot). Sem estes
    # caminhos a listagem faz meia dúzia de queries por linha.
    list_select_related = (
        "prontuario__paciente",
        "medico",
        "consulta__paciente",
        "consulta__slot",
    )
    date_hierarchy = "criado_em"
    ordering = ("-id",)
    list_per_page = 50

    @admin.display(description="corrige", boolean=True)
    def corrige(self, obj: Evolucao) -> bool:
        """Marca as evoluções que retificam uma anterior — o único caminho de
        correção numa tabela que não aceita ``UPDATE``."""
        return obj.evolucao_anterior_id is not None

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        """Todos os campos concretos, sempre — a tabela é append-only."""
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(LogAcesso)
class LogAcessoAdmin(admin.ModelAdmin):
    """Trilha de auditoria LGPD — **somente leitura**.

    Responde à pergunta do titular ("quem acessou meus dados?") e à
    investigação de incidente ("o que este usuário andou vendo?"). Ambas são
    leitura; nenhuma linha nasce nesta tela.
    """

    list_display = ("criado_em", "usuario", "acao", "paciente", "ip")
    list_filter = ("acao", "criado_em", "usuario")
    # ``user_agent`` é ``CharField`` (não NCLOB) de propósito — ver o model —,
    # então entra na busca da investigação de incidente sem risco.
    search_fields = ("paciente__nome", "usuario__username", "ip", "user_agent")
    list_select_related = ("usuario", "paciente")
    date_hierarchy = "criado_em"
    ordering = ("-id",)
    list_per_page = 50

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        """Todos os campos concretos, sempre — a tabela é auditoria."""
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

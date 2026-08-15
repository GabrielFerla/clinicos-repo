"""Admin do app ``core``.

O Django Admin é a UI do CRM no MVP1 (ADR-0005), então vale investir aqui em
vez de escrever telas custom.

Além do admin do usuário, este módulo hospeda :class:`RestritoAoMedicoMixin` —
a peça de permissão por perfil `[S2-10]` que os admins de ``crm``, ``agenda`` e
``prontuario`` reutilizam. Ele mora aqui, e não em cada app, porque a regra é
uma só: quem define o recorte é ``Usuario.perfil``, que é model do ``core``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Usuario

if TYPE_CHECKING:
    from apps.crm.models import Medico


def medico_vinculado(usuario: object) -> Medico | None:
    """Devolve o ``Medico`` ligado a este usuário, ou ``None`` se não houver.

    O acesso reverso do ``OneToOneField`` (``Medico.usuario``, ``related_name=
    "medico"``) levanta ``Medico.DoesNotExist`` quando não há vínculo — e não
    devolve ``None``, que é a intuição errada que já custou ``AttributeError``
    em produção alheia. Capturamos ``ObjectDoesNotExist`` (a superclasse) para
    não precisar importar ``apps.crm.models`` aqui: ``core`` é o app de baixo na
    pilha, e importá-lo do ``crm`` fecharia um ciclo.

    Args:
        usuario: Instância de ``Usuario`` — ou ``AnonymousUser``, que também
            responde ``None`` em vez de estourar.

    Returns:
        O médico vinculado, ou ``None``.
    """
    try:
        return usuario.medico
    except (ObjectDoesNotExist, AttributeError):
        return None


class RestritoAoMedicoMixin:
    """Recorta o ``get_queryset`` do Admin ao que pertence ao médico logado `[S2-10]`.

    Regra, na ordem em que é aplicada:

    1. **Superusuário vê tudo** — inclusive um superusuário cujo ``perfil`` seja
       ``MEDICO``. Sem essa saída antecipada, um administrador que também
       atende perderia acesso ao painel inteiro.
    2. **``ADMIN`` e ``RECEPCAO`` veem tudo.** A recepção precisa da base
       inteira para marcar, remarcar e atender ao telefone.
    3. **``MEDICO`` vê só o que passa por ele**, via :meth:`restringir_ao_medico`.
    4. **``MEDICO`` sem ``Medico`` vinculado não vê nada.** É o caso perigoso:
       um perfil ``MEDICO`` recém-criado, ainda sem vínculo, não pode "cair no
       else" e enxergar a clínica toda. O default é o fechado — ``qs.none()``.

    Filtrar o ``get_queryset`` cobre **também** a tela de detalhe: o
    ``ModelAdmin.get_object`` do Django lê deste mesmo queryset, então
    ``/admin/agenda/consulta/<id>/change/`` de um objeto fora do recorte devolve
    302 para o index com "não existe", nunca o objeto. Não é dedução — está
    coberto em ``apps/core/test_permissoes.py`` `[S2-18]`.

    O que o mixin **não** faz é decidir *o que* é "do médico": cada Admin
    implementa :meth:`restringir_ao_medico`, porque o caminho até ``MEDICO``
    muda de model para model (direto em ``Consulta``, via consultas em
    ``Paciente``, via paciente em ``Prontuario``).
    """

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        queryset = super().get_queryset(request)
        usuario = request.user
        if usuario.is_superuser or not getattr(usuario, "eh_medico", False):
            return queryset
        medico = medico_vinculado(usuario)
        if medico is None:
            return queryset.none()
        return self.restringir_ao_medico(queryset, medico)

    def restringir_ao_medico(self, queryset: QuerySet, medico: Medico) -> QuerySet:
        """Recorta ``queryset`` ao que pertence a ``medico``. Cada Admin implementa.

        Raises:
            NotImplementedError: sempre. Herdar o mixin sem implementar isto
                seria pior que não herdá-lo — o Admin pareceria protegido e não
                estaria —, então o erro é ruidoso de propósito.
        """
        raise NotImplementedError(
            f"{type(self).__name__} herda RestritoAoMedicoMixin mas não implementa "
            "restringir_ao_medico(); sem isso o recorte por médico não existe."
        )


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin do usuário custom.

    Estende o ``UserAdmin`` padrão em vez de declarar os fieldsets do zero:
    assim as telas de troca de senha, permissões e grupos continuam
    funcionando. Só acrescentamos o campo ``perfil``.
    """

    model = Usuario

    list_display = ("username", "first_name", "last_name", "email", "perfil", "is_active")
    list_filter = ("perfil", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)

    # ``UserAdmin.fieldsets`` é uma tupla de tuplas; concatenamos em vez de
    # reescrever para não perder nada que o Django adicione em versões futuras.
    fieldsets = UserAdmin.fieldsets + (("ClinicOS", {"fields": ("perfil",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("ClinicOS", {"fields": ("perfil",)}),)

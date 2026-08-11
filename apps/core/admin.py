"""Admin do app ``core``.

O Django Admin é a UI do CRM no MVP1 (ADR-0005), então vale investir aqui em
vez de escrever telas custom.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


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

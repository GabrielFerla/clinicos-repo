"""Models transversais do ClinicOS.

Hoje só o usuário custom mora aqui. Models de domínio ficam nos apps
correspondentes (``crm``, ``agenda``, ``chatbot``, ``prontuario``).
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuário do sistema — equipe da clínica, não paciente.

    Herda de :class:`~django.contrib.auth.models.AbstractUser` (e não de
    ``AbstractBaseUser``) de propósito: o MVP1 usa o Django Admin como UI do
    CRM (ver ADR-0005), e o Admin já vem pronto para o contrato do
    ``AbstractUser``. Trocar a base depois é migration de tabela; adicionar
    campos, não. Começamos pelo caminho reversível.

    ``AUTH_USER_MODEL`` aponta para cá desde a S1-6. Enquanto este model não
    existiu, **nada** que resolvesse o usuário funcionava — nem ``migrate``,
    nem ``pytest``, nem o carregamento do Admin.

    Paciente **não** é usuário: no MVP1 ele não tem login (ver ``ESCOPO.md``).
    A relação com o chatbot é via ``crm.Lead``, não via autenticação.
    """

    class Perfil(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        MEDICO = "MEDICO", "Médico"
        RECEPCAO = "RECEPCAO", "Recepção"

    perfil = models.CharField(
        "perfil",
        max_length=10,
        choices=Perfil.choices,
        default=Perfil.RECEPCAO,
        help_text="Define o que o usuário enxerga e edita no painel interno.",
    )

    class Meta:
        db_table = "USUARIO"
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["username"]

    def __str__(self) -> str:
        nome = self.get_full_name().strip()
        return f"{nome} ({self.username})" if nome else self.username

    @property
    def eh_medico(self) -> bool:
        """Atalho de leitura para templates e checagens de permissão."""
        return self.perfil == self.Perfil.MEDICO

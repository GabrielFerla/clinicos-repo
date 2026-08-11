"""Models da agenda — slots de atendimento.

Só ``AgendaSlot`` entra no Bloco 1A: é o que a tool ``buscar_slots`` lê. A
``AgendaRegra`` (regra recorrente semanal que *gera* os slots) fica para a
Sprint 3 — o chatbot desta entrega apenas consulta disponibilidade, não cria
nem reserva nada.

Ver ``docs/CHAT_MVP.md`` (Bloco 1A) e ``docs/ARQUITETURA.md``
("Anti-overbooking").
"""

from __future__ import annotations

from django.db import models


class AgendaSlot(models.Model):
    """Janela de atendimento de um médico em uma data e horário.

    A constraint ``UK_SLOT_MEDICO_HORARIO`` é a barreira anti-overbooking
    exigida pela ``ARQUITETURA.md``: mesmo com duas requisições concorrentes,
    o banco recusa o segundo slot no mesmo ``(médico, data, hora de início)``.
    A garantia mora no schema, não na aplicação — um bug de código ou um
    ``INSERT`` fora do ORM não consegue furá-la. `[S1-11]`

    Attributes:
        status: Estado do slot. ``RESERVADO`` marca slot tomado por uma
            consulta; ``BLOQUEADO`` é indisponibilidade manual (férias,
            cirurgia, congresso). Só ``LIVRE`` aparece para o paciente.
    """

    class Status(models.TextChoices):
        LIVRE = "LIVRE", "Livre"
        RESERVADO = "RESERVADO", "Reservado"
        BLOQUEADO = "BLOQUEADO", "Bloqueado"

    medico = models.ForeignKey(
        "crm.Medico",
        # PROTECT: um médico com agenda não pode sumir do banco e levar o
        # histórico junto (retenção CFM). Desativar usa ``Medico.ativo``.
        on_delete=models.PROTECT,
        related_name="slots",
        verbose_name="médico",
        # Coberto pela coluna-líder de UK_SLOT_MEDICO_HORARIO; o índice
        # automático do Django seria redundante e com nome autogerado.
        db_index=False,
    )
    data = models.DateField("data")
    hora_inicio = models.TimeField("hora de início")
    hora_fim = models.TimeField("hora de término")
    status = models.CharField(
        "status",
        max_length=10,
        choices=Status.choices,
        default=Status.LIVRE,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        db_table = "AGENDA_SLOT"
        verbose_name = "slot de agenda"
        verbose_name_plural = "slots de agenda"
        ordering = ["data", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["medico", "data", "hora_inicio"],
                name="UK_SLOT_MEDICO_HORARIO",
                violation_error_message="Este médico já tem um slot neste dia e horário.",
            ),
        ]
        indexes = [
            # A consulta quente do chatbot é "slots LIVRE a partir de hoje":
            # filtra por data e status, nesta ordem. Nome explícito porque o
            # Oracle trunca identificadores em 30 caracteres.
            models.Index(fields=["data", "status"], name="IDX_SLOT_DATA_STATUS"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.medico.nome} — {self.data:%d/%m/%Y} "
            f"{self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M} ({self.status})"
        )

    @property
    def esta_livre(self) -> bool:
        """Atalho de leitura para templates e para as tools do chatbot."""
        return self.status == self.Status.LIVRE

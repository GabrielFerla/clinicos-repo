"""Popula o banco com dados realistas de clínica oftalmológica — S1-16 (parcial).

Idempotente por natureza: usa ``get_or_create`` em tudo e só cria slots que
faltam, então rodar de novo não duplica nada. É por isso que
``infra/scripts/setup.sh`` pode chamá-lo em todo ``make setup``.

Escopo: só o que as ferramentas do chatbot consultam — especialidades, médicos,
slots e FAQ. Pacientes e consultas entram quando os models existirem.

Depois deste comando, rode ``reindexar_faq`` para gerar os embeddings; sem
isso a busca semântica não devolve nada.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.agenda.models import AgendaSlot
from apps.chatbot.models import FaqVector
from apps.crm.models import Especialidade, Medico, MedicoEspecialidade

ARQUIVO_FAQ = Path(__file__).resolve().parents[3] / "core" / "fixtures" / "faq_oftalmologia.json"

ESPECIALIDADES: list[tuple[str, str, str]] = [
    ("Oftalmologia Geral", "oftalmologia-geral", "Consulta completa, refração e triagem."),
    ("Retina", "retina", "Doenças da retina: diabetes, descolamento e degeneração macular."),
    ("Glaucoma", "glaucoma", "Diagnóstico e acompanhamento da pressão intraocular."),
    ("Córnea", "cornea", "Ceratocone, transplante e avaliação para cirurgia refrativa."),
    (
        "Oftalmologia Pediátrica",
        "oftalmologia-pediatrica",
        "Atendimento de crianças a partir de 6 meses.",
    ),
]

MEDICOS: list[tuple[str, str, str, list[str]]] = [
    ("Dra. Ana Lima", "12345", "RS", ["Oftalmologia Geral", "Retina"]),
    ("Dr. Bruno Carvalho", "23456", "RS", ["Glaucoma", "Oftalmologia Geral"]),
    ("Dra. Carla Menezes", "34567", "RS", ["Córnea"]),
    ("Dr. Diego Rocha", "45678", "RS", ["Oftalmologia Pediátrica", "Oftalmologia Geral"]),
    ("Dra. Elisa Prado", "56789", "RS", ["Retina", "Glaucoma"]),
]

# Grade de atendimento: seg-sex 08h-19h, sáb 08h-13h (bate com a FAQ).
HORARIOS_SEMANA = [dt.time(h, m) for h in range(8, 19) for m in (0, 30)]
HORARIOS_SABADO = [dt.time(h, m) for h in range(8, 13) for m in (0, 30)]
DIAS_A_GERAR = 14


class Command(BaseCommand):
    help = "Cria especialidades, médicos, slots futuros e FAQs da clínica piloto."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        especialidades = self._criar_especialidades()
        medicos = self._criar_medicos(especialidades)
        slots = self._criar_slots(medicos)
        faqs = self._criar_faqs()

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(especialidades)} especialidades, {len(medicos)} médicos, "
                f"{slots} slots e {faqs} FAQs."
            )
        )
        self.stdout.write(
            "Próximo passo: `python manage.py reindexar_faq` para gerar os embeddings."
        )

    def _criar_especialidades(self) -> dict[str, Especialidade]:
        criadas: dict[str, Especialidade] = {}
        for nome, slug, descricao in ESPECIALIDADES:
            obj, _ = Especialidade.objects.get_or_create(
                nome=nome, defaults={"slug": slug, "descricao": descricao}
            )
            criadas[nome] = obj
        return criadas

    def _criar_medicos(self, especialidades: dict[str, Especialidade]) -> list[Medico]:
        medicos: list[Medico] = []
        for nome, crm, uf, nomes_esp in MEDICOS:
            medico, _ = Medico.objects.get_or_create(
                crm_numero=crm, crm_uf=uf, defaults={"nome": nome}
            )
            for indice, nome_esp in enumerate(nomes_esp):
                MedicoEspecialidade.objects.get_or_create(
                    medico=medico,
                    especialidade=especialidades[nome_esp],
                    defaults={"principal": indice == 0},
                )
            medicos.append(medico)
        return medicos

    def _criar_slots(self, medicos: list[Medico]) -> int:
        """Gera slots livres nos próximos dias úteis, sem duplicar.

        Cada médico atende em dias alternados para a agenda não ficar
        artificialmente cheia — e para a tool ``buscar_slots`` ter casos em que
        um período realmente não tem vaga.
        """
        hoje = timezone.localdate()
        criados = 0
        for offset in range(1, DIAS_A_GERAR + 1):
            data = hoje + dt.timedelta(days=offset)
            if data.weekday() == 6:  # domingo: fechado
                continue
            horarios = HORARIOS_SABADO if data.weekday() == 5 else HORARIOS_SEMANA
            for indice, medico in enumerate(medicos):
                if (offset + indice) % 2:
                    continue
                for hora in horarios:
                    _, novo = AgendaSlot.objects.get_or_create(
                        medico=medico,
                        data=data,
                        hora_inicio=hora,
                        defaults={
                            "hora_fim": (
                                dt.datetime.combine(data, hora) + dt.timedelta(minutes=30)
                            ).time(),
                            "status": AgendaSlot.Status.LIVRE,
                        },
                    )
                    criados += int(novo)
        return criados

    def _criar_faqs(self) -> int:
        if not ARQUIVO_FAQ.exists():
            self.stdout.write(self.style.WARNING(f"FAQ não encontrada em {ARQUIVO_FAQ}"))
            return 0
        registros = json.loads(ARQUIVO_FAQ.read_text(encoding="utf-8"))
        for item in registros:
            FaqVector.objects.get_or_create(
                pergunta=item["pergunta"],
                defaults={
                    "resposta": item["resposta"],
                    "categoria": item.get("categoria", ""),
                },
            )
        return len(registros)

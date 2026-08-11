"""Gera e grava os embeddings da FAQ — tarefa S5-16.

Idempotente: só reprocessa a linha cujo conteúdo, modelo ou dimensão mudaram
(ver ``FaqVector.precisa_reindexar``). O spike apagava tudo e reinseria a cada
execução, o que joga fora trabalho e cria uma janela em que a busca não acha
nada.

Uso::

    docker compose run --rm django python manage.py reindexar_faq
    docker compose run --rm django python manage.py reindexar_faq --forcar
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.chatbot.models import FaqVector
from apps.chatbot.repositories.faq import FAQRepository, VetorIncompativelError
from apps.chatbot.services.embeddings import get_embedding_provider

# Lote pequeno de propósito: o Ollama serializa requests (`-np 1`), então lote
# grande não paraleliza nada e só aumenta o tempo até o primeiro commit.
TAMANHO_LOTE = 16


class Command(BaseCommand):
    help = "Gera embeddings dos FAQs ativos e grava em FAQ_VECTOR.EMBEDDING."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--forcar",
            action="store_true",
            help="Reprocessa todos os FAQs ativos, mesmo os já indexados e sem alteração.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        modelo = settings.EMBEDDING_MODEL
        dim = settings.EMBEDDING_DIM
        forcar: bool = options["forcar"]

        ativos = list(FaqVector.objects.filter(ativo=True).order_by("pk"))
        if not ativos:
            self.stdout.write(self.style.WARNING("Nenhum FAQ ativo. Rode `seed_initial` antes."))
            return

        pendentes = ativos if forcar else [f for f in ativos if f.precisa_reindexar(modelo, dim)]
        if not pendentes:
            self.stdout.write(
                self.style.SUCCESS(f"{len(ativos)} FAQs já indexados com {modelo} — nada a fazer.")
            )
            return

        self.stdout.write(f"Indexando {len(pendentes)} de {len(ativos)} FAQs com {modelo}...")
        provider = get_embedding_provider()
        total = 0

        for inicio in range(0, len(pendentes), TAMANHO_LOTE):
            lote = pendentes[inicio : inicio + TAMANHO_LOTE]
            # Só a PERGUNTA é vetorizada. A busca compara pergunta-do-usuário
            # com pergunta-cadastrada; embedar a resposta junto dilui o sinal.
            try:
                vetores = provider.gerar([f.pergunta for f in lote])
            except Exception as exc:  # noqa: BLE001
                raise CommandError(f"Falha ao gerar embeddings: {exc}") from exc

            for faq, vetor in zip(lote, vetores, strict=True):
                try:
                    # O vetor vai por SQL cru (o ORM não conhece VECTOR) e os
                    # metadados pelo ORM — na mesma transação, senão uma falha
                    # no meio deixa a linha marcada como indexada sem vetor.
                    with transaction.atomic():
                        FAQRepository.gravar_embedding(faq.pk, vetor)
                        faq.embedding_modelo = modelo
                        faq.embedding_dim = dim
                        faq.embedding_gerado_em = timezone.now()
                        faq.conteudo_hash = faq.calcular_conteudo_hash()
                        faq.save(
                            update_fields=[
                                "embedding_modelo",
                                "embedding_dim",
                                "embedding_gerado_em",
                                "conteudo_hash",
                                "atualizado_em",
                            ]
                        )
                except VetorIncompativelError as exc:
                    raise CommandError(str(exc)) from exc
                total += 1

            self.stdout.write(f"  {total}/{len(pendentes)}")

        self.stdout.write(self.style.SUCCESS(f"{total} FAQs indexados com {modelo} ({dim}d)."))

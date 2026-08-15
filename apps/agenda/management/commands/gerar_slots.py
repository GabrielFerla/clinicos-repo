"""Expande as regras de agenda em slots concretos — tarefa S3-3.

``AgendaRegra`` só *descreve* a janela semanal ("toda segunda, 08:00–12:00,
consultas de 30 minutos"); quem materializa essa descrição em linhas de
``AgendaSlot`` é este comando. Ele é a porta de entrada automática da agenda: a
`[S3-4]` vai chamá-lo diariamente pelo Celery Beat, e o primeiro item do DoD da
sprint ("recepção cria regra de agenda semanal e visualiza slots gerados nos
próximos 60 dias") é literalmente a saída dele.

Quatro decisões que valem ser lidas antes de mexer:

* **``dia_semana`` é 0 = segunda … 6 = domingo**, igual a ``date.weekday()`` e
  deliberadamente diferente do lookup ``__week_day`` do Django (1 = domingo).
  É por isso que o casamento de dia acontece em Python (``data.weekday()``) e
  não num ``filter`` do ORM — ver a docstring de ``AgendaRegra``. Converter
  índice de dia da semana é a origem clássica do erro de um dia aqui.
* **Só cria; nunca altera nem apaga.** Slot ``RESERVADO`` tem consulta em cima e
  slot ``BLOQUEADO`` é indisponibilidade que alguém declarou à mão — reescrever
  qualquer um dos dois a partir da regra desfaria trabalho humano. Regra que
  mudou *depois* de já ter gerado slots é assunto da `[S3-5]`; este comando não
  tem opinião sobre o passado.
* **Idempotente por construção.** Os slots já gravados na janela são lidos uma
  vez (``(medico, data, hora_inicio)``, a chave de ``UK_SLOT_MEDICO_HORARIO``) e
  os candidatos que já existem nem chegam a virar ``INSERT``. A constraint
  continua sendo a rede de segurança para execuções concorrentes, tratada em
  :meth:`Command._inserir`.
* **Procedência.** Todo slot gerado aponta para a regra de origem em
  ``AgendaSlot.regra``. Sem isso a `[S3-5]` não teria como perguntar "quais
  slots vieram desta regra que acabou de mudar?".

Uso::

    docker compose run --rm django python manage.py gerar_slots
    docker compose run --rm django python manage.py gerar_slots --dias 90
    docker compose run --rm django python manage.py gerar_slots --medico 3 --dry-run
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.agenda.models import AgendaRegra, AgendaSlot

DIAS_PADRAO = 60

# Tamanho do lote de INSERT. O Django ainda reduz este número via
# ``bulk_batch_size`` quando o backend tem limite de binds (é o caso do Oracle),
# então ele é um teto, não uma promessa.
TAMANHO_LOTE = 500

# Chave de ``UK_SLOT_MEDICO_HORARIO``: ``(medico_id, data, hora_inicio)``.
ChaveSlot = tuple[int, dt.date, dt.time]


def _vigente_em(regra: AgendaRegra, data: dt.date) -> bool:
    """Diz se ``regra`` vale na data informada.

    ``vigencia_fim`` nulo é o caso normal — regra sem prazo de término.

    Args:
        regra: Regra semanal a testar.
        data: Dia concreto do calendário.

    Returns:
        ``True`` se a data cai dentro da vigência da regra.
    """
    if data < regra.vigencia_inicio:
        return False
    return regra.vigencia_fim is None or data <= regra.vigencia_fim


def _horarios(regra: AgendaRegra, data: dt.date) -> Iterator[tuple[dt.time, dt.time]]:
    """Fatia a janela da regra nas consultas de um dia.

    Um slot só é emitido se couber **inteiro** antes de ``hora_fim``: uma janela
    de 08:00–10:00 com consultas de 45 minutos rende 08:00–08:45 e 09:00–09:45 e
    para por aí, porque o terceiro slot terminaria às 10:45 e invadiria o que
    vem depois (almoço, outro médico, o fim do expediente).

    A aritmética é feita em ``datetime`` combinado com ``data``, e não em
    ``time`` puro: somar ``timedelta`` a um ``time`` não existe em Python, e
    comparar só o componente de hora daria falso positivo numa janela que
    atravessasse a meia-noite (23:00 + 2h volta como 01:00, que é "menor" que
    qualquer ``hora_fim``).

    Não há risco de laço infinito: ``CK_AGENDA_REGRA_DURACAO`` garante
    ``duracao_consulta_min > 0`` no schema, então o cursor sempre avança.

    Args:
        regra: Regra que descreve a janela e a duração de cada consulta.
        data: Dia para o qual as horas serão calculadas.

    Yields:
        Pares ``(hora_inicio, hora_fim)`` de cada consulta que cabe na janela.
    """
    passo = dt.timedelta(minutes=regra.duracao_consulta_min)
    folga = dt.timedelta(minutes=regra.intervalo_min)
    limite = dt.datetime.combine(data, regra.hora_fim)

    inicio = dt.datetime.combine(data, regra.hora_inicio)
    while inicio + passo <= limite:
        fim = inicio + passo
        yield inicio.time(), fim.time()
        inicio = fim + folga


class Command(BaseCommand):
    help = "Expande as regras de agenda ativas em slots livres para os próximos dias."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dias",
            type=int,
            default=DIAS_PADRAO,
            help=(
                f"Quantos dias à frente gerar, contados a partir de hoje "
                f"(padrão: {DIAS_PADRAO}). A janela inclui as duas pontas."
            ),
        )
        parser.add_argument(
            "--medico",
            type=int,
            default=None,
            metavar="ID",
            help="Gera apenas as regras deste médico. Sem o argumento, processa todos.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra quantos slots seriam criados sem gravar nada.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dias: int = options["dias"]
        medico_id: int | None = options["medico"]
        dry_run: bool = options["dry_run"]

        if dias < 0:
            raise CommandError("--dias tem que ser zero ou mais.")

        inicio = timezone.localdate()
        fim = inicio + dt.timedelta(days=dias)

        regras = self._regras_em_escopo(medico_id)
        if not regras:
            alvo = f" para o médico {medico_id}" if medico_id is not None else ""
            self.stdout.write(
                self.style.WARNING(f"Nenhuma regra de agenda ativa{alvo} — nada a gerar.")
            )
            return

        self.stdout.write(
            f"Gerando slots de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} "
            f"a partir de {len(regras)} regras ativas..."
        )

        novos, ja_existiam, sobrepostos = self._planejar(regras, inicio, fim)

        if sobrepostos:
            # Janelas sobrepostas no mesmo dia (08:00–12:00 e 09:00–10:00) são
            # legítimas no schema e a validação delas é da [S3-1]; aqui elas
            # apenas convergem para o mesmo slot, e o primeiro a chegar vence.
            self.stdout.write(
                self.style.WARNING(
                    f"{sobrepostos} horários apareceram em mais de uma regra "
                    f"(janelas sobrepostas) e foram gerados uma vez só."
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] {len(novos)} slots seriam criados, {ja_existiam} já existem. "
                    f"Nada foi gravado."
                )
            )
            return

        escopo = self._escopo_gravado(medico_id, inicio, fim)
        antes = escopo.count()
        self._inserir(novos)
        # Contagem por diferença, e não pelo retorno do ``bulk_create``: com
        # ``ignore_conflicts`` o retorno não distingue o que entrou do que foi
        # descartado (e no Oracle nem sequer traz as PKs).
        criados = escopo.count() - antes

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(regras)} regras processadas: {criados} slots criados, "
                f"{ja_existiam} já existiam."
            )
        )

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def _regras_em_escopo(self, medico_id: int | None) -> list[AgendaRegra]:
        """Carrega as regras ativas, opcionalmente de um médico só.

        A vigência **não** entra no filtro do banco de propósito: ela é checada
        por data em :func:`_vigente_em`, e duplicar a mesma condição em SQL só
        criaria um segundo lugar onde o limite pode ficar errado. A tabela tem
        ordem de grandeza de dezenas de linhas (ver ``AgendaRegra.Meta``), então
        lê-la inteira uma vez por execução é mais barato que qualquer índice.
        """
        regras = AgendaRegra.objects.filter(ativo=True)
        if medico_id is not None:
            regras = regras.filter(medico_id=medico_id)
        return list(regras.order_by("medico_id", "dia_semana", "hora_inicio"))

    def _escopo_gravado(self, medico_id: int | None, inicio: dt.date, fim: dt.date):
        """Slots já gravados dentro da janela — a base das contagens."""
        escopo = AgendaSlot.objects.filter(data__gte=inicio, data__lte=fim)
        if medico_id is not None:
            escopo = escopo.filter(medico_id=medico_id)
        return escopo

    # ------------------------------------------------------------------
    # Planejamento
    # ------------------------------------------------------------------

    def _planejar(
        self, regras: list[AgendaRegra], inicio: dt.date, fim: dt.date
    ) -> tuple[list[AgendaSlot], int, int]:
        """Monta os slots que faltam, sem tocar em nada que já esteja gravado.

        Args:
            regras: Regras ativas em escopo.
            inicio: Primeiro dia da janela (hoje).
            fim: Último dia da janela, incluído.

        Returns:
            A tripla ``(slots a inserir, quantos já existiam no banco, quantos
            colidiram entre regras sobrepostas nesta mesma execução)``.
        """
        medicos = {regra.medico_id for regra in regras}
        # Uma consulta só para a janela inteira, em vez de um ``exists()`` por
        # slot: são milhares de candidatos por execução.
        existentes: set[ChaveSlot] = set(
            AgendaSlot.objects.filter(
                medico_id__in=medicos, data__gte=inicio, data__lte=fim
            ).values_list("medico_id", "data", "hora_inicio")
        )

        planejados: set[ChaveSlot] = set()
        novos: list[AgendaSlot] = []
        ja_existiam = 0
        sobrepostos = 0

        data = inicio
        while data <= fim:
            # ``data.weekday()`` direto: a convenção de ``AgendaRegra`` é a mesma
            # (0 = segunda … 6 = domingo). Não converter.
            dia_semana = data.weekday()
            for regra in regras:
                if regra.dia_semana != dia_semana or not _vigente_em(regra, data):
                    continue
                for hora_inicio, hora_fim in _horarios(regra, data):
                    chave: ChaveSlot = (regra.medico_id, data, hora_inicio)
                    if chave in existentes:
                        ja_existiam += 1
                        continue
                    if chave in planejados:
                        sobrepostos += 1
                        continue
                    planejados.add(chave)
                    novos.append(
                        AgendaSlot(
                            medico_id=regra.medico_id,
                            regra=regra,
                            data=data,
                            hora_inicio=hora_inicio,
                            hora_fim=hora_fim,
                            status=AgendaSlot.Status.LIVRE,
                        )
                    )
            data += dt.timedelta(days=1)

        return novos, ja_existiam, sobrepostos

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def _inserir(self, novos: list[AgendaSlot]) -> None:
        """Grava os slots novos, absorvendo colisão com o que já estiver lá.

        O caminho rápido é ``bulk_create(..., ignore_conflicts=True)``, apoiado
        em ``UK_SLOT_MEDICO_HORARIO``. **O Oracle não tem esse caminho**: o
        backend do Django declara ``supports_ignore_conflicts = False`` (não há
        equivalente a ``ON CONFLICT DO NOTHING`` no ``INSERT``), e passar a flag
        levanta ``NotSupportedError`` — ou seja, o comando morreria justamente no
        banco de produção. Por isso a decisão é do backend, não nossa.

        No caminho sem ``ignore_conflicts``, a colisão só acontece se outra
        execução gravar o mesmo horário entre o ``SELECT`` de :meth:`_planejar` e
        este ``INSERT`` (o Celery Beat da `[S3-4]` rodando junto de uma execução
        manual, tipicamente). Quando isso ocorre, o lote inteiro é refeito linha
        a linha para que os slots sem conflito entrem mesmo assim — cada um no
        seu próprio savepoint, porque no Oracle um ``IntegrityError`` invalida a
        transação corrente.
        """
        if not novos:
            return

        if connection.features.supports_ignore_conflicts:
            AgendaSlot.objects.bulk_create(novos, batch_size=TAMANHO_LOTE, ignore_conflicts=True)
            return

        for comeco in range(0, len(novos), TAMANHO_LOTE):
            lote = novos[comeco : comeco + TAMANHO_LOTE]
            try:
                with transaction.atomic():
                    AgendaSlot.objects.bulk_create(lote, batch_size=TAMANHO_LOTE)
            except IntegrityError:
                for slot in lote:
                    try:
                        with transaction.atomic():
                            slot.save(force_insert=True)
                    except IntegrityError:
                        # Slot que outra execução gravou primeiro: é exatamente o
                        # que ``ignore_conflicts`` faria — segue em frente.
                        continue

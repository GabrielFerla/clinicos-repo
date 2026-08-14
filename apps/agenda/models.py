"""Models da agenda — regras de disponibilidade, slots e consultas.

``AgendaSlot`` é a janela concreta que a tool ``buscar_slots`` lê (Bloco 1A do
``docs/CHAT_MVP.md``). ``AgendaRegra`` é a regra recorrente semanal a partir da
qual esses slots são *gerados* — só a modelagem entra aqui `[S1-8]`; a geração
propriamente dita (command ``gerar_slots``) é `[S3-3]`. ``Consulta`` é a
ocupação de um slot por um paciente; ela mora neste app, e não no ``crm``,
porque a ``ARQUITETURA.md`` põe o ``AgendamentoService`` em
``apps/agenda/services/agendamento.py`` — o model fica junto do service que o
escreve `[S3-7]`.

Valem as mesmas convenções de schema descritas na docstring de
``apps/crm/models.py``: ``db_table`` em UPPER_SNAKE_CASE, nome explícito em
**todo** índice e constraint (o Oracle trunca identificadores em 30 caracteres
e nome truncado quebra o rollback), e nada de ``TextField`` em coluna que
apareça em ``WHERE``/``ORDER BY``.

Ver ``docs/ARQUITETURA.md`` ("Modelo de dados" e "Anti-overbooking").
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q


class AgendaRegra(models.Model):
    """Regra recorrente semanal de disponibilidade de um médico.

    É o molde dos slots: "toda terça, das 08:00 às 12:00, consultas de 30
    minutos com 10 de intervalo, valendo de 01/09/2026 em diante". A expansão
    da regra em linhas de ``AgendaSlot`` é `[S3-3]` — este model não gera nada,
    só descreve.

    **Convenção de ``dia_semana``:** 0 = segunda … 6 = domingo, igual a
    ``datetime.date.weekday()``. Deliberadamente *não* é a convenção do lookup
    ``__week_day`` do Django (1 = domingo): a geração de slots percorre datas em
    Python, então casar com ``date.weekday()`` elimina a conversão — e conversão
    de índice de dia da semana é fonte clássica de erro de um dia.

    **Unicidade:** a chave é ``(medico, dia_semana, hora_inicio,
    vigencia_inicio)``, e não ``(medico, dia_semana)``. Um médico legitimamente
    tem mais de uma regra no mesmo dia (manhã e tarde), então a hora de início
    faz parte da identidade da janela. ``vigencia_inicio`` entra porque é assim
    que `[S3-5]` versiona uma regra que mudou no meio do caminho: fecha-se a
    regra vigente com ``vigencia_fim`` e cria-se outra, mesmo dia e mesmo
    horário, começando no dia seguinte. Sem a data na chave, esse versionamento
    seria recusado pelo banco.

    O que a constraint **não** impede é sobreposição de janelas no mesmo dia
    (08:00–12:00 e 09:00–10:00 convivem). Isso exigiria uma exclusion
    constraint por intervalo, que o Oracle não tem; a checagem fica na camada de
    validação em `[S3-1]`.

    Attributes:
        medico: Dono da regra. ``PROTECT`` pelo mesmo motivo do slot — médico
            com agenda não some do banco levando o histórico junto.
        dia_semana: Dia da semana em que a regra se repete (ver convenção
            acima).
        duracao_consulta_min: Tamanho de cada consulta gerada, em minutos.
        intervalo_min: Folga entre uma consulta e a seguinte. Default 0 —
            atendimento em sequência é o caso comum.
        vigencia_fim: Último dia em que a regra vale. ``NULL`` = regra sem
            prazo, que é o normal; a data só aparece quando a agenda muda.
        ativo: Soft delete (ver ``ARQUITETURA.md``). Desativar a regra para de
            gerar slots novos sem apagar os que já foram gerados.
    """

    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 0, "Segunda-feira"
        TERCA = 1, "Terça-feira"
        QUARTA = 2, "Quarta-feira"
        QUINTA = 3, "Quinta-feira"
        SEXTA = 4, "Sexta-feira"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    medico = models.ForeignKey(
        "crm.Medico",
        on_delete=models.PROTECT,
        related_name="regras",
        verbose_name="médico",
        # Coberto pela coluna-líder de UK_AGENDA_REGRA_JANELA; o índice
        # automático do Django seria redundante (ORA-01408 no Oracle) e com
        # nome autogerado.
        db_index=False,
    )
    dia_semana = models.PositiveSmallIntegerField(
        "dia da semana",
        choices=DiaSemana.choices,
        help_text="0 = segunda … 6 = domingo (mesma convenção de date.weekday()).",
    )
    hora_inicio = models.TimeField("hora de início")
    hora_fim = models.TimeField("hora de término")
    duracao_consulta_min = models.PositiveSmallIntegerField(
        "duração da consulta (min)",
        help_text="Tamanho de cada slot gerado, em minutos.",
    )
    intervalo_min = models.PositiveSmallIntegerField(
        "intervalo entre consultas (min)",
        default=0,
        help_text="Folga entre o fim de uma consulta e o início da próxima.",
    )
    vigencia_inicio = models.DateField("início da vigência")
    vigencia_fim = models.DateField(
        "fim da vigência",
        null=True,
        blank=True,
        help_text="Deixe em branco para regra sem prazo de término.",
    )
    ativo = models.BooleanField(
        "ativa",
        default=True,
        help_text="Desmarque para parar de gerar slots sem apagar o histórico.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        db_table = "AGENDA_REGRA"
        verbose_name = "regra de agenda"
        verbose_name_plural = "regras de agenda"
        ordering = ["medico", "dia_semana", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["medico", "dia_semana", "hora_inicio", "vigencia_inicio"],
                name="UK_AGENDA_REGRA_JANELA",
                violation_error_message=(
                    "Este médico já tem uma regra neste dia da semana, "
                    "com este horário de início e esta vigência."
                ),
            ),
            models.CheckConstraint(
                condition=Q(hora_fim__gt=F("hora_inicio")),
                name="CK_AGENDA_REGRA_HORARIO",
                violation_error_message="A hora de término tem que ser maior que a de início.",
            ),
            models.CheckConstraint(
                condition=Q(duracao_consulta_min__gt=0),
                name="CK_AGENDA_REGRA_DURACAO",
                violation_error_message="A duração da consulta tem que ser maior que zero.",
            ),
            # Vigência invertida é o mesmo tipo de erro de digitação que o
            # horário invertido, e o custo de barrar no schema é o mesmo.
            models.CheckConstraint(
                condition=Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=F("vigencia_inicio")),
                name="CK_AGENDA_REGRA_VIGENCIA",
                violation_error_message="O fim da vigência não pode ser antes do início.",
            ),
        ]
        # Sem índice por ``dia_semana``: a tabela tem ordem de grandeza de
        # dezenas de linhas (poucas regras por médico) e o `gerar_slots` lê o
        # conjunto inteiro uma vez por execução — full scan é mais barato que
        # índice aqui.

    def __str__(self) -> str:
        return (
            f"{self.medico.nome} — {self.get_dia_semana_display()} "
            f"{self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}"
        )


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
        regra: Regra que gerou o slot, quando houve uma. É rastreabilidade de
            procedência: `[S3-5]` precisa saber quais slots vieram de uma regra
            que mudou depois. ``NULL`` é legítimo — slots semeados à mão ou
            criados antes desta coluna não têm regra de origem.
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
    regra = models.ForeignKey(
        AgendaRegra,
        # PROTECT: a regra é a procedência do slot. Apagá-la deixaria slots
        # órfãos e cegaria o tratamento de bordas de [S3-5]; desativar usa
        # ``AgendaRegra.ativo``.
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="slots",
        verbose_name="regra de origem",
        # Esta FK **não** é coberta por UK_SLOT_MEDICO_HORARIO (a coluna-líder
        # de lá é ``medico``). FK sem índice no Oracle causa lock de tabela no
        # pai durante DML, então o índice existe — só que com nome explícito,
        # em Meta.indexes.
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
            # Cobre a FK ``regra`` (ver comentário no campo) e serve à pergunta
            # de [S3-5]: "quais slots esta regra gerou?".
            models.Index(fields=["regra"], name="IDX_SLOT_REGRA"),
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


class Consulta(models.Model):
    """Agendamento de um paciente em um slot de um médico.

    **Segunda barreira anti-overbooking.** ``UK_SLOT_MEDICO_HORARIO`` garante
    que não existam dois *slots* no mesmo ``(médico, data, hora)``; o
    ``OneToOneField`` para :class:`AgendaSlot` garante que não existam duas
    *consultas* no mesmo slot. São camadas distintas: a primeira protege a
    geração da agenda, a segunda protege o agendamento. Sem ela, dois pedidos
    concorrentes para o mesmo horário livre passariam pela constraint do slot
    (que já existia e não é violada por um INSERT em ``CONSULTA``) e o paciente
    descobriria a colisão só na recepção. A garantia mora no schema, não na
    aplicação — a transação serializável de `[S3-7]` é otimização de
    experiência, não a fonte da integridade.

    O ``OneToOneField`` implica ``unique=True`` no campo, que é a única exceção
    à regra "unicidade sempre via ``UniqueConstraint`` nomeada" (ver docstring
    de ``apps/crm/models.py``): o Django não permite desligar o ``unique`` de um
    ``OneToOneField``, e declarar uma ``UniqueConstraint`` adicional sobre a
    mesma coluna estouraria ``ORA-01408``. O trade-off aceito é o nome
    autogerado dessa única constraint.

    Attributes:
        slot: Janela ocupada. ``PROTECT`` porque apagar o slot apagaria a prova
            de quando a consulta foi marcada; slot indisponível usa
            ``AgendaSlot.Status.BLOQUEADO``.
        medico: **Desnormalização deliberada** de ``slot.medico``. A tela
            "minha agenda" `[S3-12]` e o filtro por médico no Admin são as
            leituras mais frequentes do sistema, e sem esta coluna toda uma
            delas exigiria join com ``AGENDA_SLOT`` só para chegar ao dono do
            horário. O custo é a invariante ``consulta.medico == slot.medico``,
            que o banco não impõe (exigiria trigger ou FK composta) e que o
            ``AgendamentoService`` `[S3-7]` é responsável por preencher a partir
            do próprio slot — nenhum caller deve informar o médico à mão.
        observacoes: Anotação operacional curta da recepção ("paciente prefere
            chegar mais cedo", "acompanhante"). ``CharField`` e **não**
            ``TextField``: a busca do Admin varre esta coluna, e ``NCLOB`` não
            entra em ``WHERE``/``ORDER BY`` no Oracle. Texto clínico não passa
            por aqui — ele é append-only e mora em ``EVOLUCAO``.
        origem: Por onde a consulta entrou. É o denominador da métrica de
            conversão do chatbot `[S5-28]`.
    """

    class Status(models.TextChoices):
        AGENDADA = "AGENDADA", "Agendada"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        REALIZADA = "REALIZADA", "Realizada"
        CANCELADA = "CANCELADA", "Cancelada"
        FALTOU = "FALTOU", "Faltou"

    class Origem(models.TextChoices):
        CHAT = "CHAT", "Chatbot"
        RECEPCAO = "RECEPCAO", "Recepção"
        SITE = "SITE", "Site"

    paciente = models.ForeignKey(
        "crm.Paciente",
        # PROTECT: consulta é histórico clínico (retenção CFM de 20 anos).
        # Arquivar paciente usa ``Paciente.ativo``.
        on_delete=models.PROTECT,
        related_name="consultas",
        verbose_name="paciente",
        # FK não coberta por outra constraint; sem índice o Oracle trava a
        # tabela pai durante DML. O índice existe em Meta.indexes, nomeado.
        db_index=False,
    )
    slot = models.OneToOneField(
        AgendaSlot,
        on_delete=models.PROTECT,
        related_name="consulta",
        verbose_name="slot",
        # O UNIQUE do OneToOne já é respaldado por índice; um segundo
        # CREATE INDEX sobre a mesma coluna daria ORA-01408 no Oracle.
        db_index=False,
    )
    medico = models.ForeignKey(
        "crm.Medico",
        on_delete=models.PROTECT,
        related_name="consultas",
        verbose_name="médico",
        db_index=False,  # coberto por IDX_CONSULTA_MEDICO (ver Meta.indexes)
        help_text="Cópia de slot.medico — preenchida pelo AgendamentoService, não pelo caller.",
    )
    status = models.CharField(
        "status",
        max_length=10,
        choices=Status.choices,
        default=Status.AGENDADA,
    )
    origem = models.CharField(
        "origem",
        max_length=10,
        choices=Origem.choices,
        default=Origem.RECEPCAO,
        help_text="RECEPCAO é o caminho manual; CHAT e SITE são preenchidos por quem agenda.",
    )
    observacoes = models.CharField(
        "observações",
        max_length=500,
        blank=True,
        help_text=(
            "Anotação operacional da recepção. Limitada a 500 caracteres para não "
            "virar NCLOB no Oracle. Registro clínico vai em EVOLUCAO."
        ),
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        db_table = "CONSULTA"
        verbose_name = "consulta"
        verbose_name_plural = "consultas"
        # Por ``-id``, e não por ``-criado_em``: a PK é sequencial, então a
        # ordem é a mesma (mais recentes primeiro) e sai do índice da chave
        # primária — um índice a menos para sustentar o ORDER BY de toda
        # listagem do Admin.
        ordering = ["-id"]
        indexes = [
            # "Histórico deste paciente" — tela de atendimento e pré-consulta.
            # Também cobre a FK ``paciente``.
            models.Index(fields=["paciente"], name="IDX_CONSULTA_PACIENTE"),
            # "Minha agenda" [S3-12]: é esta coluna que justifica a
            # desnormalização de ``medico``. Também cobre a FK.
            models.Index(fields=["medico"], name="IDX_CONSULTA_MEDICO"),
            # Painéis operacionais filtram por status (confirmadas de hoje,
            # faltas do mês).
            models.Index(fields=["status"], name="IDX_CONSULTA_STATUS"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.paciente.nome} — {self.slot.data:%d/%m/%Y} "
            f"{self.slot.hora_inicio:%H:%M} ({self.status})"
        )

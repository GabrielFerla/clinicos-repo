"""Models do prontuário — agregador clínico, evoluções append-only e auditoria LGPD.

Três tabelas com três regimes de escrita bem diferentes, e é essa diferença
que explica quase toda decisão deste módulo:

* :class:`Prontuario` é um **agregador**: uma linha por paciente, praticamente
  imutável na prática porque não carrega nada além do vínculo.
* :class:`Evolucao` é **append-only por exigência do CFM**. A garantia não mora
  aqui: mora no trigger ``TRG_EVOLUCAO_IMUTAVEL`` (migration ``0002``), que
  recusa ``UPDATE`` e ``DELETE`` no banco `[S1-10]`. Este model é desenhado
  *para* esse regime — sem ``atualizado_em``, com o hash de autoria calculado
  antes do ``INSERT``, e com correção via nova linha encadeada.
* :class:`LogAcesso` é **auditoria LGPD** (``ARQUITETURA.md``, "Conformidade
  legal"): quem viu, exportou ou editou o dado de qual paciente. A tabela nasce
  aqui `[S1-8]`; o middleware que a popula é da Sprint 6 — nenhum código deste
  módulo escreve nela.

Valem as mesmas convenções de schema descritas na docstring de
``apps/crm/models.py``: ``db_table`` em UPPER_SNAKE_CASE, nome explícito em
**todo** índice e constraint (o Oracle trunca identificadores em 30 caracteres
e nome truncado quebra o rollback), e nada de ``TextField`` em coluna que
apareça em ``WHERE``/``ORDER BY`` — lá vira ``NCLOB``, que não é ordenável nem
indexável. ``Evolucao.texto`` é a exceção legítima: é campo só lido, nunca
filtrado.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone


class Prontuario(models.Model):
    """Agregador clínico do paciente — uma linha por paciente, e só.

    A ``ARQUITETURA.md`` o define exatamente assim ("agregador único por
    paciente"), e a tentação de engordá-lo com alergias, medicações em uso e
    histórico familiar é justamente o que o desenho recusa: qualquer um desses
    campos é dado que *muda*, e dado clínico que muda pertence a
    :class:`Evolucao`, que é append-only e datada. Uma coluna ``ALERGIAS``
    aqui seria um registro clínico sem autor, sem data e sobrescrevível — o
    oposto do que o CFM pede.

    O que ele resolve é a ponte: ``PACIENTE`` é cadastro (CRM, LGPD) e
    ``EVOLUCAO`` é registro clínico (CFM, retenção de 20 anos). O prontuário no
    meio dá um alvo estável de permissão e de auditoria — "acesso ao prontuário
    de X" é uma frase que existe no schema, não só na conversa.

    Attributes:
        paciente: Dono do prontuário. ``OneToOneField`` porque a unicidade é a
            definição da entidade — dois prontuários para o mesmo paciente
            partiriam o histórico em dois, que é a falha clássica do domínio.
            ``PROTECT`` pelo mesmo motivo de toda FK para ``Paciente``: apagar
            paciente com prontuário violaria a retenção de 20 anos; arquivar
            usa ``Paciente.ativo``.
    """

    paciente = models.OneToOneField(
        "crm.Paciente",
        on_delete=models.PROTECT,
        related_name="prontuario",
        verbose_name="paciente",
        # O ``unique`` implícito do OneToOne já é respaldado por índice; um
        # segundo CREATE INDEX sobre a mesma coluna estoura
        # ``ORA-01408: such column list already indexed`` (o SQLite aceita
        # calado). Mesma exceção documentada em ``agenda.Consulta.slot``: o
        # nome dessa única constraint é autogerado porque o Django não permite
        # desligar o ``unique`` de um ``OneToOneField``.
        db_index=False,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        db_table = "PRONTUARIO"
        verbose_name = "prontuário"
        verbose_name_plural = "prontuários"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Prontuário de {self.paciente.nome}"


class Evolucao(models.Model):
    """Registro clínico de um atendimento. **Append-only**, garantido no banco.

    O trigger ``TRG_EVOLUCAO_IMUTAVEL`` (migration ``0002``) recusa ``UPDATE``
    e ``DELETE`` nesta tabela com ``ORA-20001``. A escolha de pôr a regra no
    banco, e não em ``save()``, é da ``ARQUITETURA.md``: assim nem um bug grave
    da aplicação, nem um SQL fora do ORM, nem uma injeção conseguem corromper o
    registro. O model **não** repete a checagem em Python — repetir daria a
    falsa impressão de que a aplicação é a fonte da garantia, e no SQLite dos
    testes ela seria uma regra sem lastro no schema.

    Como se corrige um erro num registro imutável
    ---------------------------------------------
    Pelo caminho que a própria mensagem do trigger prescreve: "use nova
    evolução com referência à anterior". É o que :attr:`evolucao_anterior`
    materializa — a linha nova aponta para a que ela corrige, e as duas
    sobrevivem. O histórico fica auditável (dá para ver o que se pensava antes
    e o que mudou), que é exatamente o que uma retificação médica exige.

    Por que **não** existe ``atualizado_em``
    ----------------------------------------
    A coluna seria mentira estrutural: o banco proíbe ``UPDATE``, então ela
    nasceria igual a ``criado_em`` e nunca mudaria. Pior, sugeriria a quem
    lesse o model que atualizar a linha é uma operação prevista — e o primeiro
    ``save()`` de rotina descobriria, em produção, que não é.

    Por que ``criado_em`` não é ``auto_now_add``
    --------------------------------------------
    ``auto_now_add`` só atribui o valor **dentro** do ``save()``, ao montar o
    ``INSERT``. Como :attr:`conteudo_hash` precisa do timestamp (ver abaixo) e
    a tabela nunca poderá ser atualizada para preencher o hash depois, o
    carimbo tem que existir *antes* de o ``INSERT`` ser montado. ``default=
    timezone.now`` dá isso: o valor nasce junto com a instância, e hash e
    carimbo entram no banco no mesmo e único ``INSERT``. ``editable=False``
    preserva o comportamento de ``auto_now_add`` no Admin e nos forms.

    Attributes:
        prontuario: Prontuário a que a evolução pertence. ``PROTECT``:
            retenção CFM de 20 anos.
        medico: **Autor** do registro. ``PROTECT`` porque autoria é requisito
            de conformidade (``ARQUITETURA.md``, "CFM — autoria"): evolução sem
            autor identificável não é prontuário válido. Não é anulável nem
            desnormalizável — quem assinou, assinou.
        consulta: Atendimento que originou a evolução, quando houve um.
            ``SET_NULL`` e não ``PROTECT``: a evolução é o registro clínico e
            precisa sobreviver ao agendamento que a originou — perder o texto
            porque alguém removeu a consulta seria destruir prontuário para
            salvar agenda. ``NULL`` também cobre o caso legítimo da evolução
            registrada fora de consulta marcada (retorno de exame, contato
            telefônico).
        texto: Registro clínico livre. Único ``TextField`` do módulo, e
            legítimo: nunca entra em ``WHERE``/``ORDER BY``, é sempre lido pela
            chave. Vira ``CLOB`` no Oracle sem prejuízo.
        evolucao_anterior: Evolução que esta corrige ou complementa (ver acima).
            ``SET_NULL`` para que a corrente degrade em vez de arrastar linhas
            junto — mas na prática o elo nunca se rompe, já que o trigger
            impede o ``DELETE`` do alvo.
        conteudo_hash: SHA-256 de ``texto + autor + timestamp``. Ver
            :meth:`calcular_conteudo_hash`.
    """

    prontuario = models.ForeignKey(
        Prontuario,
        on_delete=models.PROTECT,
        related_name="evolucoes",
        verbose_name="prontuário",
        # FK não coberta por outra constraint; sem índice o Oracle trava a
        # tabela pai durante DML. O índice existe em Meta.indexes, nomeado.
        db_index=False,
    )
    medico = models.ForeignKey(
        "crm.Medico",
        on_delete=models.PROTECT,
        related_name="evolucoes",
        verbose_name="médico",
        db_index=False,  # coberto por IDX_EVOLUCAO_MEDICO
        help_text="Autor do registro. Entra no hash de autoria exigido pelo CFM.",
    )
    consulta = models.ForeignKey(
        "agenda.Consulta",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evolucoes",
        verbose_name="consulta",
        db_index=False,  # coberto por IDX_EVOLUCAO_CONSULTA
    )
    texto = models.TextField(
        "texto",
        help_text="Registro clínico. Só é lido, nunca filtrado — pode ser CLOB no Oracle.",
    )
    evolucao_anterior = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="correcoes",
        verbose_name="evolução anterior",
        db_index=False,  # coberto por IDX_EVOLUCAO_ANTERIOR
        help_text=(
            "Preencha ao corrigir ou complementar um registro anterior — é o "
            "único caminho de retificação, já que a tabela é append-only."
        ),
    )
    conteudo_hash = models.CharField(
        "hash do conteúdo",
        max_length=64,
        blank=True,
        help_text="SHA-256 de texto+autor+timestamp. Preenchido no INSERT; prova de autoria (CFM).",
    )
    criado_em = models.DateTimeField(
        "criado em",
        default=timezone.now,
        editable=False,
        help_text="Carimbo da autoria. Entra no hash, por isso não é auto_now_add.",
    )

    class Meta:
        db_table = "EVOLUCAO"
        verbose_name = "evolução"
        verbose_name_plural = "evoluções"
        # Por ``-id``, e não por ``-criado_em``: a PK é sequencial e a tabela é
        # append-only, então a ordem é rigorosamente a mesma (mais recente
        # primeiro) e sai do índice da chave primária — um índice a menos para
        # sustentar o ORDER BY.
        ordering = ["-id"]
        indexes = [
            # "As evoluções deste prontuário" — a leitura quente da tela de
            # atendimento. Também cobre a FK.
            models.Index(fields=["prontuario"], name="IDX_EVOLUCAO_PRONTUARIO"),
            # "O que este médico registrou" — auditoria de autoria. Cobre a FK.
            models.Index(fields=["medico"], name="IDX_EVOLUCAO_MEDICO"),
            models.Index(fields=["consulta"], name="IDX_EVOLUCAO_CONSULTA"),
            # Cobre a self-FK e serve à pergunta inversa: "esta evolução foi
            # corrigida depois?".
            models.Index(fields=["evolucao_anterior"], name="IDX_EVOLUCAO_ANTERIOR"),
        ]

    def __str__(self) -> str:
        return f"Evolução de {self.criado_em:%d/%m/%Y} por {self.medico.nome}"

    def save(self, *args: object, **kwargs: object) -> None:
        """Preenche :attr:`conteudo_hash` antes do ``INSERT``, se ainda não houver.

        É aqui e não no caller porque é a única janela que existe: depois do
        ``INSERT`` a linha é intocável, então um hash esquecido seria um hash
        perdido para sempre. O ``if`` preserva um valor já calculado — cenário
        de importação de prontuário legado, em que o hash vem da origem.
        """
        if not self.conteudo_hash:
            self.conteudo_hash = self.calcular_conteudo_hash()
        super().save(*args, **kwargs)

    def calcular_conteudo_hash(self) -> str:
        """Calcula o SHA-256 que serve de prova de autoria desta evolução.

        Cobre **texto + autor + timestamp**, os três elementos que a
        ``ARQUITETURA.md`` lista em "CFM — autoria". O texto sozinho não
        bastaria: dois médicos podem registrar a mesma frase, e um hash igual
        para autores diferentes não prova autoria nenhuma. O autor entra como
        ``medico_id`` (a identidade estável no banco) e não como nome, que é
        editável em ``MEDICO`` e faria o hash "mudar" sem que a evolução
        mudasse.

        Segue o mesmo padrão de ``chatbot.FaqVector.calcular_conteudo_hash``,
        inclusive o separador ``\\x1f`` (unit separator), que impede colisão
        entre triplas diferentes cuja concatenação daria o mesmo texto.

        Não é assinatura digital — não há segredo envolvido, então ele detecta
        adulteração acidental e serve de identidade do conteúdo, mas quem
        pudesse reescrever a linha poderia recalcular o hash. A barreira contra
        reescrita é o trigger, não este método.

        Returns:
            Digest hexadecimal de 64 caracteres.
        """
        carimbo = self.criado_em.isoformat() if self.criado_em else ""
        conteudo = f"{self.texto}\x1f{self.medico_id}\x1f{carimbo}"
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


class LogAcesso(models.Model):
    """Trilha de auditoria LGPD: quem tocou no dado de qual paciente, e quando.

    A ``ARQUITETURA.md`` a lista em "Conformidade legal" como a implementação
    de "LGPD — auditoria". O alvo é o **paciente**, e não o prontuário, porque
    o dado sensível vaza por várias telas — cadastro, agenda, prontuário — e a
    pergunta do titular ("quem acessou meus dados?") é sobre ele, não sobre uma
    tabela.

    **Quem escreve aqui é o middleware da Sprint 6.** Nesta sprint entra só a
    tabela `[S1-8]`; nenhum código deste módulo insere linha. Registrar acesso
    à mão em cada view seria garantia de esquecimento — e trilha com buraco não
    é trilha.

    Como :class:`Evolucao`, é append-only por natureza (log que se edita não
    audita nada), mas **sem trigger**: a imutabilidade obrigatória por lei é a
    do prontuário, e o trigger tem custo em toda DML. Aqui a proteção é o Admin
    somente-leitura e a ausência de qualquer caminho de escrita fora do
    middleware.

    Attributes:
        usuario: Quem acessou. ``PROTECT``: apagar o usuário levaria junto a
            prova de quem viu o dado, que é precisamente o que a trilha existe
            para preservar. Desligar acesso é ``is_active=False``.
        paciente: Titular do dado acessado. ``PROTECT`` pelo mesmo motivo.
        acao: O que foi feito. ``EDITOU`` cobre alteração de cadastro do
            paciente — **não** de evolução, que o banco não permite alterar.
        ip: Origem da requisição. Anulável: requisição interna (comando,
            task Celery) não tem IP de cliente, e inventar ``0.0.0.0`` seria
            pior que registrar a ausência.
        user_agent: Cabeçalho ``User-Agent`` da requisição, truncado em 300
            caracteres. ``CharField`` e **não** ``TextField`` de propósito:
            a investigação de incidente filtra e agrupa por esta coluna, e
            ``NCLOB`` não entra em ``WHERE``/``ORDER BY`` no Oracle.
    """

    class Acao(models.TextChoices):
        VISUALIZOU = "VISUALIZOU", "Visualizou"
        EXPORTOU = "EXPORTOU", "Exportou"
        EDITOU = "EDITOU", "Editou"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acessos",
        verbose_name="usuário",
        db_index=False,  # coberto por IDX_LOG_ACESSO_USUARIO
    )
    paciente = models.ForeignKey(
        "crm.Paciente",
        on_delete=models.PROTECT,
        related_name="acessos",
        verbose_name="paciente",
        db_index=False,  # coberto por IDX_LOG_ACESSO_PACIENTE
    )
    acao = models.CharField(
        "ação",
        max_length=10,
        choices=Acao.choices,
    )
    ip = models.GenericIPAddressField(
        "IP",
        null=True,
        blank=True,
        help_text="Vazio quando o acesso não veio de uma requisição HTTP.",
    )
    user_agent = models.CharField(
        "user agent",
        max_length=300,
        blank=True,
        help_text="Truncado em 300 caracteres para não virar NCLOB no Oracle.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        db_table = "LOG_ACESSO"
        verbose_name = "log de acesso"
        verbose_name_plural = "logs de acesso"
        ordering = ["-id"]
        indexes = [
            # "Quem acessou os dados deste paciente?" — a pergunta do titular
            # (LGPD, direito de acesso). Também cobre a FK ``paciente``.
            models.Index(fields=["paciente"], name="IDX_LOG_ACESSO_PACIENTE"),
            # Recorte temporal da investigação de incidente ("acessos da última
            # semana"), e o corte que a política de retenção do log vai usar.
            models.Index(fields=["criado_em"], name="IDX_LOG_ACESSO_DATA"),
            # Não pedido pelo recorte funcional, mas obrigatório pela convenção
            # do módulo: FK sem índice nenhum faz o Oracle travar a tabela pai
            # durante DML. Serve também a "o que este usuário andou vendo?".
            models.Index(fields=["usuario"], name="IDX_LOG_ACESSO_USUARIO"),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} {self.get_acao_display().lower()} {self.paciente.nome}"

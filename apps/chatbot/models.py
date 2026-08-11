"""Models do chatbot — base de conhecimento vetorial e auditoria de turnos.

Ver ``docs/CHAT_MVP.md`` (Bloco 1A e 1B).

**A coluna ``EMBEDDING`` não é declarada aqui, de propósito.** Ela é
``VECTOR(384, FLOAT32)``, um tipo que o ORM do Django não conhece, e entra por
migration separada guardada por ``vendor == "oracle"`` (Bloco 1B). Assim o
SQLite do CI cria ``FAQ_VECTOR`` sem a coluna e todos os testes de model,
admin e tools continuam rodando. O único uso do vetor é ``VECTOR_DISTANCE``
num ``ORDER BY``, que não tem expressão ORM — a query é SQL cru de qualquer
forma, então um ``VectorField`` customizado não pagaria o próprio custo.
"""

from __future__ import annotations

import hashlib
import uuid

from django.db import models


class FaqVector(models.Model):
    """Pergunta frequente da clínica, indexada para busca semântica.

    Os três campos ``embedding_*`` existem por causa de uma invariante que
    falha em silêncio: indexar com um modelo de embedding e consultar com
    outro devolve **lixo sem erro nenhum** — as distâncias continuam saindo,
    só que sem significado. Guardando modelo e dimensão na própria linha, o
    ``buscar_faq`` consegue **recusar** o resultado quando divergem, em vez de
    responder com confiança errada.

    ``conteudo_hash`` torna a reindexação idempotente: o comando compara o
    hash do texto atual com o gravado e só chama o provedor de embeddings
    quando mudou. O spike fazia ``DELETE`` + insert a cada rodada `[S5-16]`.

    Attributes:
        pergunta: ``CharField`` (não ``TextField``) porque é o campo buscado e
            ordenado no Admin — ``NCLOB`` não serve em ``WHERE``/``ORDER BY``.
        resposta: Texto livre, só lido. Pode ser ``CLOB`` sem prejuízo.
        embedding_gerado_em: ``None`` enquanto a linha nunca foi indexada.
    """

    pergunta = models.CharField("pergunta", max_length=500)
    resposta = models.TextField("resposta")
    categoria = models.CharField(
        "categoria",
        max_length=50,
        blank=True,
        help_text="Agrupador livre (convênios, horários, exames…). Usado só para curadoria.",
    )
    ativo = models.BooleanField(
        "ativa",
        default=True,
        help_text="Somente FAQs ativas são indexadas e consultadas pelo chatbot.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    embedding_gerado_em = models.DateTimeField(
        "embedding gerado em",
        null=True,
        blank=True,
        help_text="Vazio significa que a linha ainda não tem vetor na coluna EMBEDDING.",
    )
    embedding_modelo = models.CharField(
        "modelo do embedding",
        max_length=100,
        blank=True,
        help_text="Modelo que gerou o vetor. Consultar com outro modelo devolve lixo silencioso.",
    )
    embedding_dim = models.PositiveIntegerField(
        "dimensão do embedding",
        null=True,
        blank=True,
        help_text="Dimensão do vetor gravado. Deve bater com EMBEDDING_DIM das settings.",
    )
    conteudo_hash = models.CharField(
        "hash do conteúdo",
        max_length=64,
        blank=True,
        help_text="SHA-256 de pergunta+resposta na indexação. É o que torna o reindex idempotente.",
    )

    class Meta:
        db_table = "FAQ_VECTOR"
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"
        ordering = ["categoria", "pergunta"]
        indexes = [
            # Toda busca do chatbot filtra por ``ativo``. Nome explícito
            # porque o Oracle trunca identificadores em 30 caracteres.
            models.Index(fields=["ativo"], name="IDX_FAQ_ATIVO"),
        ]

    def __str__(self) -> str:
        return self.pergunta

    def calcular_conteudo_hash(self) -> str:
        """Calcula o SHA-256 do conteúdo indexável desta FAQ.

        Serve de chave de comparação para a reindexação: se o valor calculado
        for igual ao ``conteudo_hash`` gravado, o vetor continua válido e o
        provedor de embeddings não precisa ser chamado.

        O separador ``\\x1f`` (unit separator) evita colisão entre pares
        diferentes que concatenados dariam o mesmo texto.

        Returns:
            Digest hexadecimal de 64 caracteres.
        """
        conteudo = f"{self.pergunta}\x1f{self.resposta}"
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()

    def precisa_reindexar(self, modelo: str, dim: int) -> bool:
        """Diz se esta FAQ precisa ter o embedding regerado.

        Args:
            modelo: Modelo de embedding configurado agora (``EMBEDDING_MODEL``).
            dim: Dimensão configurada agora (``EMBEDDING_DIM``).

        Returns:
            ``True`` se a linha nunca foi indexada, se o texto mudou, ou se o
            vetor gravado veio de outro modelo/dimensão — os três casos em que
            confiar no vetor existente produziria ranking sem significado.
        """
        if self.embedding_gerado_em is None:
            return True
        if self.embedding_modelo != modelo or self.embedding_dim != dim:
            return True
        return self.conteudo_hash != self.calcular_conteudo_hash()


class InteracaoChat(models.Model):
    """Um turno de conversa: pergunta do paciente e resposta do assistente.

    É **auditoria**, não estado de aplicação: só escreve o ``ChatService``, e
    no Admin a tabela é somente leitura. Também é o histórico da conversa — a
    sessão do Django não serve para isso, porque ``SessionMiddleware`` fecha a
    resposta *antes* do gerador SSE ser consumido e a escrita se perde em
    silêncio `[S5-2]`.

    A PK é ``UUID`` gerada na aplicação, e não sequência do banco: o
    ``conversa_id`` circula na URL do stream (``/chat/stream/<uuid>/``), e ID
    sequencial ali seria enumerável por qualquer visitante.

    ``UK_INTERACAO_SEQ`` garante que dois turnos não ocupem a mesma posição na
    mesma conversa, o que embaralharia o histórico reenviado ao modelo.

    Attributes:
        tools_usadas: Nomes das tools chamadas neste turno.
        faq_ids: PKs de :class:`FaqVector` que fundamentaram a resposta —
            é o que permite citar fontes e auditar grounding depois.
        alucinacao_detectada: Marcado pelo validador pós-geração quando o
            texto cita horário, data ou médico que não veio das tools. A taxa
            de detecção é a métrica de grounding do projeto `[S5-26]`.
        erro: Mensagem técnica do que falhou. Fica no banco e no log; **nunca**
            vai para o browser (vazaria DSN, usuário do Oracle e caminhos).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversa_id = models.UUIDField(
        "conversa",
        help_text="Agrupa os turnos de uma mesma conversa. Validado contra a sessão (anti-IDOR).",
        # Sem ``db_index=True``: ``UK_INTERACAO_SEQ`` já é um índice composto
        # com ``conversa_id`` como coluna-líder, e serve os filtros por
        # conversa (que é o único acesso quente). Um índice extra aqui seria
        # redundante — e, pior, teria nome autogerado, exatamente o que o
        # limite de 30 caracteres do Oracle transforma em rollback quebrado.
    )
    sequencia = models.PositiveIntegerField(
        "sequência",
        default=1,
        help_text="Posição do turno dentro da conversa, começando em 1.",
    )

    pergunta = models.TextField("pergunta")
    resposta = models.TextField("resposta", blank=True)

    tools_usadas = models.JSONField("tools usadas", default=list, blank=True)
    faq_ids = models.JSONField("FAQs consultadas", default=list, blank=True)

    modelo = models.CharField("modelo", max_length=100, blank=True)
    tokens_entrada = models.PositiveIntegerField("tokens de entrada", null=True, blank=True)
    tokens_saida = models.PositiveIntegerField("tokens de saída", null=True, blank=True)
    latencia_ms = models.PositiveIntegerField(
        "latência (ms)",
        null=True,
        blank=True,
        help_text="Tempo total do turno. O TTFT é medido à parte, no stream.",
    )

    alucinacao_detectada = models.BooleanField("alucinação detectada", default=False)
    erro = models.TextField("erro", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        db_table = "INTERACAO_CHAT"
        verbose_name = "interação do chat"
        verbose_name_plural = "interações do chat"
        ordering = ["conversa_id", "sequencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversa_id", "sequencia"],
                name="UK_INTERACAO_SEQ",
                violation_error_message="Esta conversa já tem um turno nesta posição.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.conversa_id} #{self.sequencia}"

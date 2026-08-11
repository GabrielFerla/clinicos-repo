"""Models do CRM — catálogo de especialidades e corpo clínico.

Este módulo cobre apenas o subset que o chatbot precisa para responder
"quais especialidades vocês atendem?" e "quem atende retina?" (ver
``docs/CHAT_MVP.md``, Bloco 1A). ``Paciente``, ``Lead`` e ``Consulta`` ficam
fora de propósito: ``Paciente`` arrasta a decisão de CPF cifrado e merece PR
próprio.

Convenções aplicadas aqui e replicadas nos demais apps de domínio:

* ``db_table`` em UPPER_SNAKE_CASE (padrão Oracle, ver ``CONTRIBUTING.md``).
* **Todo** índice e constraint tem nome explícito. O backend Oracle do Django
  limita identificadores a 30 caracteres e trunca nomes autogerados; um nome
  truncado quebra o ``ALTER TABLE ... DROP CONSTRAINT`` do rollback.
* Nada de ``TextField`` em coluna que possa aparecer em ``WHERE``/``ORDER BY``
  — no Oracle vira ``NCLOB``, que não é ordenável nem indexável.
"""

from __future__ import annotations

from django.db import models


class Especialidade(models.Model):
    """Subespecialidade oftalmológica atendida pela clínica.

    Catálogo pequeno e estável (refrativa, catarata, retina, glaucoma, lentes
    de contato, pediátrica, plástica ocular). É a fonte do ``enum`` que a tool
    ``buscar_slots`` injeta no ``input_schema`` — restringir o vocabulário do
    modelo é a defesa mais eficaz contra parâmetro inventado.

    Attributes:
        nome: Rótulo exibido ao paciente. Único.
        slug: Identificador estável para URL e para o ``enum`` das tools.
        descricao: Texto curto de apoio. ``CharField`` e **não** ``TextField``:
            ``NCLOB`` não pode ser usado em ``WHERE``/``ORDER BY`` no Oracle.
        ativo: Soft delete — nunca apagamos linha (retenção CFM de 20 anos).
    """

    nome = models.CharField("nome", max_length=100)
    slug = models.SlugField(
        "slug",
        max_length=100,
        # `SlugField` traz `db_index=True` por padrão. Como já existe a
        # UniqueConstraint `UK_ESPECIALIDADE_SLUG` — e no Oracle toda constraint
        # UNIQUE é respaldada por um índice —, manter o default faria o Django
        # emitir um segundo CREATE INDEX sobre a mesma coluna, e a migration
        # morreria com `ORA-01408: such column list already indexed`.
        # O SQLite aceita a duplicidade calado; o Oracle não.
        db_index=False,
        help_text="Identificador estável usado em URLs e no enum das tools do chatbot.",
    )
    descricao = models.CharField(
        "descrição",
        max_length=300,
        blank=True,
        help_text="Resumo de uma linha. Limitado a 300 caracteres para não virar NCLOB no Oracle.",
    )
    ativo = models.BooleanField(
        "ativa",
        default=True,
        help_text="Desmarque para tirar do site e do chatbot sem apagar o histórico.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        db_table = "ESPECIALIDADE"
        verbose_name = "especialidade"
        verbose_name_plural = "especialidades"
        ordering = ["nome"]
        constraints = [
            # Declaradas aqui, e não com ``unique=True`` no campo, para que o
            # nome da constraint seja determinístico no Oracle (ver docstring
            # do módulo). ``violation_error_message`` preserva a mensagem
            # amigável que ``unique=True`` daria no Admin.
            models.UniqueConstraint(
                fields=["nome"],
                name="UK_ESPECIALIDADE_NOME",
                violation_error_message="Já existe uma especialidade com este nome.",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                name="UK_ESPECIALIDADE_SLUG",
                violation_error_message="Já existe uma especialidade com este slug.",
            ),
        ]

    def __str__(self) -> str:
        return self.nome


class Medico(models.Model):
    """Profissional do corpo clínico.

    O par ``(crm_numero, crm_uf)`` é a identidade real do médico: o número do
    CRM só é único dentro de um conselho estadual, então a unicidade tem que
    ser composta — ``crm_numero`` sozinho colidiria entre UFs.

    Attributes:
        crm_numero: Número do registro no CRM, sem a UF.
        crm_uf: Sigla da unidade federativa do conselho (2 letras).
        rqe: Registro de Qualificação de Especialista. Opcional — nem todo
            médico tem RQE emitido.
        ativo: Soft delete (ver ``ARQUITETURA.md``, "Soft delete").
    """

    nome = models.CharField("nome", max_length=150)
    crm_numero = models.CharField("número do CRM", max_length=20)
    crm_uf = models.CharField("UF do CRM", max_length=2)
    rqe = models.CharField(
        "RQE",
        max_length=20,
        blank=True,
        help_text="Registro de Qualificação de Especialista, quando houver.",
    )
    ativo = models.BooleanField(
        "ativo",
        default=True,
        help_text="Desmarque para tirar da agenda e do chatbot sem apagar o histórico.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    especialidades = models.ManyToManyField(
        Especialidade,
        through="MedicoEspecialidade",
        related_name="medicos",
        verbose_name="especialidades",
        blank=True,
    )

    class Meta:
        db_table = "MEDICO"
        verbose_name = "médico"
        verbose_name_plural = "médicos"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["crm_numero", "crm_uf"],
                name="UK_MEDICO_CRM",
                violation_error_message="Já existe um médico com este CRM nesta UF.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.nome} (CRM {self.crm_completo})"

    @property
    def crm_completo(self) -> str:
        """CRM no formato usado em documentos e no site: ``12345/SP``."""
        return f"{self.crm_numero}/{self.crm_uf}"


class MedicoEspecialidade(models.Model):
    """Vínculo N:N entre médico e especialidade.

    Model explícito (``through``) em vez de M2M automático porque o vínculo
    carrega dado próprio: ``principal`` marca a especialidade que aparece
    primeiro no site e nas respostas do chatbot.

    Attributes:
        principal: Especialidade de destaque do médico. Não há constraint de
            "no máximo uma principal por médico" — no Oracle isso exigiria
            índice único parcial via expressão, e a regra é frouxa demais para
            justificar. O Admin é quem orienta o preenchimento.
    """

    medico = models.ForeignKey(
        Medico,
        on_delete=models.CASCADE,
        related_name="vinculos_especialidade",
        verbose_name="médico",
        # Coberto pela coluna-líder de UK_MEDICO_ESPEC; o índice automático do
        # Django seria redundante e teria nome autogerado.
        db_index=False,
    )
    especialidade = models.ForeignKey(
        Especialidade,
        # PROTECT e não CASCADE: apagar uma especialidade não pode apagar
        # silenciosamente o histórico do corpo clínico.
        on_delete=models.PROTECT,
        related_name="vinculos_medico",
        verbose_name="especialidade",
        # FK sem índice no Oracle causa lock de tabela no pai durante DML;
        # o índice existe, só que com nome explícito (ver Meta.indexes).
        db_index=False,
    )
    principal = models.BooleanField(
        "principal",
        default=False,
        help_text="Especialidade de destaque do médico no site e no chatbot.",
    )

    class Meta:
        db_table = "MEDICO_ESPECIALIDADE"
        verbose_name = "especialidade do médico"
        verbose_name_plural = "especialidades do médico"
        ordering = ["medico", "-principal", "especialidade"]
        constraints = [
            models.UniqueConstraint(
                fields=["medico", "especialidade"],
                name="UK_MEDICO_ESPEC",
                violation_error_message="Este médico já está vinculado a esta especialidade.",
            ),
        ]
        indexes = [
            models.Index(fields=["especialidade"], name="IDX_MED_ESPEC_ESPEC"),
        ]

    def __str__(self) -> str:
        marcador = " (principal)" if self.principal else ""
        return f"{self.medico.nome} — {self.especialidade.nome}{marcador}"

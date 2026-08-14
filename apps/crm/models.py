"""Models do CRM — catálogo de especialidades, corpo clínico e pacientes.

``Especialidade``/``Medico``/``MedicoEspecialidade`` nasceram do subset que o
chatbot precisa para responder "quais especialidades vocês atendem?" e "quem
atende retina?" (ver ``docs/CHAT_MVP.md``, Bloco 1A). ``Paciente`` entrou
depois (S1-8), trazendo junto a decisão de CPF cifrado — ver a docstring da
classe. ``Lead`` fecha o app com o funil do CRM (S1-8/S5-22). ``Consulta`` fica
em ``apps/agenda`` — é lá que mora o ``AgendamentoService`` que a escreve.

Convenções aplicadas aqui e replicadas nos demais apps de domínio:

* ``db_table`` em UPPER_SNAKE_CASE (padrão Oracle, ver ``CONTRIBUTING.md``).
* **Todo** índice e constraint tem nome explícito. O backend Oracle do Django
  limita identificadores a 30 caracteres e trunca nomes autogerados; um nome
  truncado quebra o ``ALTER TABLE ... DROP CONSTRAINT`` do rollback.
* Nada de ``TextField`` em coluna que possa aparecer em ``WHERE``/``ORDER BY``
  — no Oracle vira ``NCLOB``, que não é ordenável nem indexável.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from apps.core.security.crypto import CPFCipher
from apps.core.security.hash import cpf_hash as _hmac_cpf_hash
from apps.core.security.hash import normalize_cpf

# ---------------------------------------------------------------------------
# Acesso às chaves de PII (settings → helpers de ``apps.core.security``)
# ---------------------------------------------------------------------------
# ``CPF_ENCRYPTION_KEY`` e ``CPF_HASH_PEPPER`` nascem em ``config/settings/base.py``
# com ``default=None``. Repassar esse ``None`` direto para ``CPFCipher`` ou
# ``cpf_hash`` produz ``TypeError``/``InvalidKeyError`` sem dizer *qual*
# variável falta — erro que já custou tempo de debug. Os dois helpers privados
# abaixo centralizam a leitura e traduzem qualquer defeito de configuração em
# ``ImproperlyConfigured`` com o nome da variável e como gerá-la.
#
# Não há cache proposital: os testes usam ``override_settings`` para simular
# ambiente mal configurado, e um cache de módulo faria o valor antigo vazar
# entre testes. O custo é montar um ``AESGCM`` por operação de CPF — desprezível
# frente ao round-trip do banco.

_COMO_GERAR = 'python -c "import secrets; print(secrets.token_urlsafe(32))"'


def _cpf_cipher() -> CPFCipher:
    """Constrói o ``CPFCipher`` a partir de ``settings.CPF_ENCRYPTION_KEY``.

    Raises:
        ImproperlyConfigured: se a variável estiver ausente/vazia ou não for
            uma chave base64-urlsafe de 32 bytes.
    """
    chave = getattr(settings, "CPF_ENCRYPTION_KEY", None)
    if not chave:
        raise ImproperlyConfigured(
            "CPF_ENCRYPTION_KEY não está definida. Sem ela o ClinicOS não cifra "
            "nem lê o CPF do paciente. Gere uma chave com "
            f"`{_COMO_GERAR}` e exporte no .env (ver docs/SETUP.md)."
        )
    try:
        # ``InvalidKeyError`` (chave com tamanho errado) e ``binascii.Error``
        # (base64 malformado) são ambos subclasses de ``ValueError``.
        return CPFCipher.from_urlsafe(chave)
    except ValueError as exc:
        raise ImproperlyConfigured(
            "CPF_ENCRYPTION_KEY está definida mas não é uma chave AES-256 válida: "
            f"{exc}. O valor precisa ser base64-urlsafe de exatamente 32 bytes — "
            f"gere um novo com `{_COMO_GERAR}`."
        ) from exc


def _cpf_pepper() -> bytes:
    """Devolve ``settings.CPF_HASH_PEPPER`` como ``bytes``, que é o que ``cpf_hash`` exige.

    A conversão é explícita porque django-environ entrega ``str`` e
    ``apps.core.security.hash.cpf_hash`` recebe ``bytes`` — passar a ``str``
    direto levanta ``TypeError`` genérico.

    O pepper é tratado como **material secreto opaco**: fazemos ``.encode()``,
    e **não** ``base64.urlsafe_b64decode()``. O que importa para o HMAC é a
    entropia dos bytes, não o alfabeto; e nem todo ambiente usa base64 (o
    ``ci.yml`` define um pepper ASCII puro, que um decode quebraria).
    A única regra é o valor ser estável — mudar o pepper invalida **todos** os
    ``cpf_hash`` já gravados.

    Raises:
        ImproperlyConfigured: se a variável estiver ausente/vazia ou curta
            demais para o mínimo de 16 bytes que ``cpf_hash`` cobra.
    """
    pepper = getattr(settings, "CPF_HASH_PEPPER", None)
    if not pepper:
        raise ImproperlyConfigured(
            "CPF_HASH_PEPPER não está definida. Sem ela não há como calcular o "
            "hash determinístico de busca do CPF. Gere um pepper com "
            f"`{_COMO_GERAR}` e exporte no .env (ver docs/SETUP.md)."
        )
    bruto = pepper.encode("utf-8") if isinstance(pepper, str) else bytes(pepper)
    if len(bruto) < 16:
        raise ImproperlyConfigured(
            f"CPF_HASH_PEPPER tem apenas {len(bruto)} bytes; o mínimo aceito é 16 "
            f"(recomendado 32). Gere um pepper novo com `{_COMO_GERAR}`."
        )
    return bruto


def _hash_de(cpf: str) -> str:
    """Hash HMAC-SHA256 do CPF normalizado — o valor que vai para ``Paciente.cpf_hash``.

    Aceita CPF com ou sem máscara: ``normalize_cpf`` reduz aos 11 dígitos antes
    do HMAC, então ``"123.456.789-09"`` e ``"12345678909"`` geram o mesmo hash.
    """
    return _hmac_cpf_hash(cpf, _cpf_pepper())


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


class PacienteManager(models.Manager):
    """Manager de ``Paciente`` com busca por CPF sem descriptografar nada.

    A tabela inteira poderia ser varrida com ``decrypt`` em cada linha para
    achar um CPF — seria O(n) e ainda traria todo mundo em claro para a
    memória do processo. O ``cpf_hash`` existe exatamente para evitar isso:
    a busca vira um ``WHERE CPF_HASH = :h`` indexado (ver ``ARQUITETURA.md``,
    "CPF: criptografia + busca").
    """

    def buscar_por_cpf(self, cpf: str) -> models.QuerySet[Paciente]:
        """Filtra pelo hash determinístico do CPF. Aceita com ou sem máscara.

        Devolve ``QuerySet`` (e não a instância) de propósito: quem quer o
        registro único chama ``.get()``/``.first()``, e quem quer restringir
        encadeia — ``buscar_por_cpf(x).filter(ativo=True)``. O soft delete
        **não** é aplicado aqui: reativar um paciente arquivado exige achá-lo,
        e a checagem de CPF duplicado tem que enxergar inativos.

        Raises:
            ValueError: se ``cpf`` não tiver 11 dígitos (via ``normalize_cpf``).
            ImproperlyConfigured: se ``CPF_HASH_PEPPER`` não estiver configurada.
        """
        return self.filter(cpf_hash=_hash_de(cpf))


class Paciente(models.Model):
    """Pessoa atendida pela clínica. Titular de dado pessoal sensível (LGPD).

    O CPF nunca existe em claro no banco. Ele mora em duas colunas derivadas:

    * ``cpf_cifrado`` — AES-256-GCM (``CPFCipher``), reversível, para exibir o
      número quando a tela realmente precisa dele.
    * ``cpf_hash`` — HMAC-SHA256 com pepper, irreversível, para **buscar** e
      para garantir unicidade. SHA-256 puro não serviria: 11 dígitos são
      força-bruta trivial sem pepper (``ARQUITETURA.md``).

    Por que a cifragem **não** está no ``save()``
    ---------------------------------------------
    Um ``save()`` que cifra sozinho precisa adivinhar se o valor que recebeu já
    está cifrado ou não — e todo ``paciente.save()`` de rotina (mudar telefone,
    marcar ``ativo=False``) passaria pelo mesmo caminho, arriscando cifrar duas
    vezes ou re-cifrar com nonce novo à toa. A entrada de CPF é rara e
    deliberada, então é um método explícito: :meth:`definir_cpf`. Fora dele não
    existe caminho que escreva CPF em claro — não há campo ``cpf`` no model e a
    property :attr:`cpf` é somente leitura.

    Por que não usamos AAD no ciphertext
    ------------------------------------
    ``CPFCipher`` aceita ``aad`` para prender o token a um registro (ex.:
    ``aad=str(paciente.id).encode()``). Aqui não usamos: :meth:`definir_cpf` é
    chamado no formulário de cadastro, **antes** do primeiro ``save()``, quando
    ainda não existe ``pk``. Usar o ``pk`` como AAD exigiria salvar duas vezes
    (uma para obter o id, outra para regravar o token) e tornaria qualquer
    migração de dados entre linhas um erro de tag. O ``cpf_hash`` único já
    impede que o mesmo CPF apareça em dois pacientes.

    Attributes:
        nome: Nome completo, como no documento.
        cpf_cifrado: Token ``base64-urlsafe(nonce || ciphertext || tag)``. Um
            CPF de 11 dígitos gera 12+11+16 = 39 bytes, ou 52 caracteres
            base64. O campo é dimensionado com folga larga (255) porque o
            formato do token é detalhe interno do ``CPFCipher`` — trocar de
            cifra não pode obrigar a uma migration de tipo de coluna.
        cpf_hash: Hexadecimal de 64 caracteres (256 bits). Único.
        data_nascimento: Usada para desambiguar homônimos e para faixa etária.
        email: Opcional — nem todo paciente informa.
        telefone: Opcional. ``CharField`` guardando o número já formatado pelo
            cadastro; sem normalização E.164 no MVP1.
        ativo: Soft delete. Nunca há ``DELETE`` físico: o CFM exige retenção
            de 20 anos do prontuário (``ARQUITETURA.md``, "Soft delete").
    """

    nome = models.CharField("nome", max_length=150)
    cpf_cifrado = models.CharField(
        "CPF (cifrado)",
        max_length=255,
        help_text="AES-256-GCM. Preenchido apenas por Paciente.definir_cpf().",
    )
    cpf_hash = models.CharField(
        "CPF (hash de busca)",
        max_length=64,
        # Já coberto pelo índice UNIQUE que respalda UK_PACIENTE_CPF_HASH. Um
        # segundo CREATE INDEX sobre a mesma coluna estoura
        # `ORA-01408: such column list already indexed` no Oracle (o SQLite
        # aceita calado). Mesmo motivo do `slug` em Especialidade.
        db_index=False,
        help_text="HMAC-SHA256 com pepper. Preenchido apenas por Paciente.definir_cpf().",
    )
    data_nascimento = models.DateField("data de nascimento")
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    ativo = models.BooleanField(
        "ativo",
        default=True,
        help_text="Desmarque para arquivar o paciente sem apagar o histórico (retenção CFM).",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    objects = PacienteManager()

    class Meta:
        db_table = "PACIENTE"
        verbose_name = "paciente"
        verbose_name_plural = "pacientes"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["cpf_hash"],
                name="UK_PACIENTE_CPF_HASH",
                violation_error_message="Já existe um paciente cadastrado com este CPF.",
            ),
        ]
        indexes = [
            # `ordering = ["nome"]` faz toda listagem do Admin ordenar por nome;
            # sem índice isso é full scan + sort a cada página.
            models.Index(fields=["nome"], name="IDX_PACIENTE_NOME"),
        ]

    def __str__(self) -> str:
        return self.nome

    def definir_cpf(self, cpf: str) -> None:
        """Normaliza, cifra e hasheia o CPF, preenchendo as duas colunas de uma vez.

        Único ponto de entrada do CPF no model. **Não** salva — o caller decide
        quando persistir, o que permite ``Paciente(...)`` → ``definir_cpf`` →
        ``save()`` num único INSERT.

        As duas colunas são preenchidas juntas justamente para nunca ficarem
        dessincronizadas: um ``cpf_hash`` de um CPF e um ``cpf_cifrado`` de
        outro seria um bug silencioso e insolúvel depois.

        Args:
            cpf: Com ou sem máscara. ``"123.456.789-09"`` e ``"12345678909"``
                produzem o mesmo hash.

        Raises:
            ValueError: se não houver exatamente 11 dígitos.
            ImproperlyConfigured: se a chave ou o pepper não estiverem
                configurados (ver ``_cpf_cipher`` e ``_cpf_pepper``).
        """
        digitos = normalize_cpf(cpf)
        # Hash primeiro: se o pepper estiver ausente, o objeto não fica com o
        # ciphertext gravado e o hash vazio.
        novo_hash = _hash_de(digitos)
        self.cpf_cifrado = _cpf_cipher().encrypt(digitos)
        self.cpf_hash = novo_hash

    @property
    def cpf(self) -> str:
        """CPF em claro (11 dígitos, sem máscara), descriptografado sob demanda.

        Somente leitura — atribuir (``paciente.cpf = ...``) levanta
        ``AttributeError``, porque gravar CPF só pode passar por
        :meth:`definir_cpf`. Devolve ``""`` quando o paciente ainda não tem CPF
        registrado.

        Raises:
            cryptography.exceptions.InvalidTag: se o token foi adulterado ou a
                chave em uso não é a que cifrou o registro.
        """
        if not self.cpf_cifrado:
            return ""
        return _cpf_cipher().decrypt(self.cpf_cifrado)

    @property
    def cpf_mascarado(self) -> str:
        """CPF ofuscado (``***.***.789-09``) para telas e logs de atendimento.

        Existe para que o caminho preguiçoso seja o seguro: quem só precisa
        confirmar identidade ao telefone não tem motivo para chamar
        :attr:`cpf` e expor os 11 dígitos.
        """
        digitos = self.cpf
        if not digitos:
            return ""
        return f"***.***.{digitos[6:9]}-{digitos[9:]}"


class Lead(models.Model):
    """Contato iniciado no chat que ainda não virou (ou acabou de virar) consulta.

    É o funil do CRM `[S5-22]`, com as cinco etapas na ordem em que o negócio
    as usa: ``NOVO`` (alguém falou com o bot) → ``QUALIFICADO`` (informou
    contato e interesse) → ``AGENDADO`` (virou :class:`agenda.Consulta`) →
    ``COMPARECEU`` (apareceu na clínica) → ``RETORNO`` (voltou ou precisa
    voltar). O model **não** impõe a sequência: um lead pode pular etapa (a
    recepção qualifica e agenda no mesmo atendimento) e pode voltar atrás
    (desmarcou). Codificar a máquina de estados no schema quebraria os dois
    casos, e a única transição automática prevista — ``AGENDADO`` quando o chat
    fecha o agendamento — é `[S5-24]`, não este model.

    Lead **não** é paciente. Só existe CPF, prontuário e retenção CFM depois da
    conversão; aqui há nome e contato voluntários, e por isso nada de
    ``UniqueConstraint``: a mesma pessoa pode voltar em outra conversa, meses
    depois, e isso é um lead novo — não um duplicado a ser recusado.

    Attributes:
        conversa_id: Conversa do chatbot que originou o lead. É ``UUIDField``
            solto e **não** FK para ``chatbot.InteracaoChat`` porque aquela
            tabela tem uma linha *por turno*: apontar para uma delas escolheria
            arbitrariamente um turno para representar o diálogo inteiro, e o
            lead se liga à conversa como um todo. O preço é não ter integridade
            referencial nessa ponta — aceito, já que ``InteracaoChat`` é
            auditoria append-only e não some. ``NULL`` cobre o lead cadastrado
            à mão pela recepção, que não veio de conversa nenhuma.
        consulta: Conversão do lead `[S5-24]`. ``SET_NULL`` e não ``PROTECT``:
            se a consulta for removida, o lead precisa sobreviver — perder o
            registro de que o contato existiu apagaria a origem da métrica de
            conversão do chatbot. O histórico de que ele chegou a agendar fica
            em ``etapa``.
        especialidade_interesse: O que a pessoa procurava. ``PROTECT`` porque
            apagar uma especialidade não pode levar o funil junto; ``NULL``
            enquanto a triagem `[S5-11]` não concluiu.
    """

    class Etapa(models.TextChoices):
        NOVO = "NOVO", "Novo"
        QUALIFICADO = "QUALIFICADO", "Qualificado"
        AGENDADO = "AGENDADO", "Agendado"
        COMPARECEU = "COMPARECEU", "Compareceu"
        RETORNO = "RETORNO", "Retorno"

    nome = models.CharField("nome", max_length=150)
    email = models.EmailField(
        "e-mail",
        blank=True,
        help_text="Opcional: o lead começa antes de a pessoa informar contato.",
    )
    telefone = models.CharField("telefone", max_length=20, blank=True)
    especialidade_interesse = models.ForeignKey(
        Especialidade,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="especialidade de interesse",
        # FK não coberta por outra constraint; sem índice o Oracle trava a
        # tabela pai durante DML. O índice existe em Meta.indexes, nomeado.
        db_index=False,
    )
    etapa = models.CharField(
        "etapa",
        max_length=12,
        choices=Etapa.choices,
        default=Etapa.NOVO,
        # Coberto por IDX_LEAD_ETAPA (o funil do Admin [S5-23] filtra por aqui);
        # ``db_index=True`` criaria um segundo índice com nome autogerado.
        db_index=False,
    )
    conversa_id = models.UUIDField(
        "conversa",
        null=True,
        blank=True,
        db_index=False,  # coberto por IDX_LEAD_CONVERSA
        help_text="UUID da conversa do chatbot (InteracaoChat.conversa_id) que originou o lead.",
    )
    consulta = models.ForeignKey(
        "agenda.Consulta",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name="consulta",
        db_index=False,  # coberto por IDX_LEAD_CONSULTA
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        db_table = "LEAD"
        verbose_name = "lead"
        verbose_name_plural = "leads"
        # Mesmo raciocínio de ``Consulta``: ``-id`` dá a ordem de chegada
        # invertida (lead mais novo primeiro, que é como o funil se lê) sem
        # exigir um índice só para o ORDER BY.
        ordering = ["-id"]
        indexes = [
            # O funil do Admin [S5-23] e o dashboard por etapa [S5-25] filtram
            # e agrupam por esta coluna.
            models.Index(fields=["etapa"], name="IDX_LEAD_ETAPA"),
            # "Esta conversa já gerou lead?" — a pergunta que [S5-12] faz a
            # cada agendamento pelo chat, para não duplicar o registro.
            models.Index(fields=["conversa_id"], name="IDX_LEAD_CONVERSA"),
            models.Index(fields=["especialidade_interesse"], name="IDX_LEAD_ESPECIALIDADE"),
            models.Index(fields=["consulta"], name="IDX_LEAD_CONSULTA"),
        ]

    def __str__(self) -> str:
        return f"{self.nome} ({self.get_etapa_display()})"

"""A única ferramenta de escrita do chatbot `[S5-12]` `[S5-24]`.

Mora em módulo separado das ferramentas de leitura de propósito. ``consultas.py``
declara na primeira linha que nada ali escreve, e essa invariante vale como
documentação: um erro de interpretação do modelo numa tool de leitura custa uma
resposta ruim; aqui custa um paciente cadastrado e um horário ocupado. Separar
os dois arquivos deixa a superfície de risco visível no ``ls``.

O que impede o modelo de inventar um agendamento
------------------------------------------------
A vaga é escolhida por ``data``, ``hora`` e ``medico`` — os mesmos três campos
que ``buscar_slots`` devolveu e que o paciente fala em voz alta —, e quem
traduz isso em PK é **o servidor**, numa consulta a ``AGENDA_SLOT`` restrita a
``status=LIVRE``. Nada aqui interpreta linguagem natural de tempo: data e hora
passam só nos formatos fixos de :data:`FORMATOS_DATA` e :data:`FORMATOS_HORA`,
então "quinta que vem" é recusado; e o que passa ainda tem que casar com uma
vaga real e livre. Sem casar, a ferramenta recusa com uma frase que o chatbot
consegue falar — nunca com um agendamento aproximado.

Até `[S5-12]` o argumento era o ``slot_id`` cru, e a defesa era o schema não
aceitar texto. Funcionava, ao custo de pôr uma PK de banco no vocabulário do
modelo: ele transcrevia o número para o paciente ("(slot_id 431)") e chegava a
pedir que o paciente *informasse* o id ao escolher. Identificar a vaga pelo que
já está na tela remove o dado da conversa em vez de tentar filtrá-lo depois —
ver o comentário em ``consultas.py``, onde o campo deixou de ser devolvido.

A escrita em si não acontece aqui: quem cria a ``Consulta`` é o
``AgendamentoService`` `[S3-7]`, com transação e lock. Esta ferramenta traduz —
argumentos do modelo viram objetos de domínio, exceções de domínio viram frases
que o chatbot consegue falar.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata
import uuid
from typing import Any

from django.db import IntegrityError, transaction

from apps.agenda.models import AgendaSlot, Consulta
from apps.agenda.services.agendamento import AgendamentoError, AgendamentoService
from apps.core.security.hash import validar_cpf
from apps.crm.models import Lead, Paciente

from .base import BaseTool, ToolError

logger = logging.getLogger(__name__)

# ``data_nascimento`` chega como string escrita pelo modelo. ``DD/MM/AAAA`` é o
# que o paciente fala e o que o prompt pede; ``AAAA-MM-DD`` é o que um modelo
# treinado em inglês devolve sozinho de vez em quando. Aceitar os dois evita
# perder o agendamento por causa de formatação — qualquer outra coisa é
# recusada, porque adivinhar se "03/04" é março ou abril erraria em silêncio.
FORMATOS_DATA = ("%d/%m/%Y", "%Y-%m-%d")

# ``hora`` chega como o modelo escreveu. "08:00" é o que ``buscar_slots``
# devolve e o que ele copia na maioria das vezes; as outras formas são as que
# aparecem quando ele reescreve com as palavras do paciente ("8h", "8h30").
FORMATOS_HORA = ("%H:%M", "%H:%M:%S", "%Hh%M", "%Hh", "%H")

# Títulos e preposições saem antes de comparar nome de médico: o cadastro tem
# "Dra. Ana Lima" e o modelo manda tanto isso quanto "Ana Lima" ou "Dra Ana".
TITULOS_MEDICO = frozenset({"dr", "dra", "drs", "doutor", "doutora"})
LIGACOES_NOME = frozenset({"de", "da", "do", "das", "dos", "e"})

MSG_HORARIO_ILEGIVEL = (
    "Não entendi a data e a hora escolhidas. Informe as duas como apareceram na "
    "lista de horários: data em DD/MM/AAAA e hora em HH:MM."
)
MSG_HORARIO_INDISPONIVEL = (
    "Esse horário não está mais disponível. Mostre outros horários livres e peça para o "
    "paciente escolher um deles."
)
MSG_DATA_INVALIDA = (
    "Não entendi a data de nascimento. Peça no formato dia/mês/ano, por exemplo 17/05/1980."
)
MSG_CPF_INVALIDO = "Esse CPF não confere. Peça para o paciente conferir os números e repetir."
MSG_FALHA = "Não consegui concluir o agendamento agora. Peça para o paciente tentar de novo."


class CriarLeadEConsultaTool(BaseTool):
    """Cadastra o paciente, ocupa o slot escolhido e fecha o lead da conversa."""

    name = "criar_lead_e_consulta"
    # Esta `description` é o guardrail que mais importa nesta ferramenta: é ela
    # que o modelo lê ao decidir entre "ainda estou coletando dados" e "posso
    # gravar". As frases sobre copiar o horário e sobre dado faltando existem
    # para impedir uso prematuro — o erro clássico é chamar com os campos em
    # branco logo depois de o paciente dizer "quero marcar".
    #
    # A frase sobre não pedir número ao paciente é o que sobrou do bug do
    # `slot_id`: o modelo pedia o id porque o schema pedia o id. Sem campo de
    # id, ele não tem o que pedir; a frase é só o cinto de segurança.
    description = (
        "Agenda a consulta de verdade. É a única ferramenta que grava algo, "
        "então use apenas no final: quando o paciente JÁ escolheu um dos "
        "horários que você mostrou e JÁ informou nome, CPF, data de nascimento "
        "e telefone. Copie data, hora e médico de um horário que você mostrou a "
        "ele — nunca invente e nunca agende horário que não foi mostrado. O "
        "paciente escolhe falando o horário: nunca peça a ele número, código "
        "nem id. Se faltar algum dado, ou se ele ainda não escolheu o horário, "
        "não chame esta ferramenta: pergunte."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "nome": {
                "type": "string",
                "description": "Nome completo do paciente, como ele informou.",
            },
            "cpf": {
                "type": "string",
                "description": "CPF do paciente, 11 dígitos. Com ou sem pontuação.",
            },
            "data_nascimento": {
                "type": "string",
                "description": "Data de nascimento no formato DD/MM/AAAA.",
            },
            "telefone": {
                "type": "string",
                "description": "Telefone de contato com DDD.",
            },
            "data": {
                "type": "string",
                "description": (
                    "Data do horário escolhido, no formato DD/MM/AAAA, copiada "
                    "da lista de horários que você mostrou ao paciente."
                ),
            },
            "hora": {
                "type": "string",
                "description": (
                    "Hora do horário escolhido, no formato HH:MM, copiada da "
                    "mesma lista. Não aceita 'de manhã' nem 'quinta que vem'."
                ),
            },
            "medico": {
                "type": "string",
                "description": (
                    "Nome do médico daquele horário, como apareceu na lista. "
                    "Sem ele não há como saber qual dos médicos do horário é."
                ),
            },
            "email": {
                "type": "string",
                "description": "E-mail do paciente, se ele informar. Opcional.",
            },
        },
        "required": ["nome", "cpf", "data_nascimento", "telefone", "data", "hora", "medico"],
    }

    def __init__(self, conversa_id: uuid.UUID | str | None = None) -> None:
        """Recebe a conversa do turno — **nunca** o modelo.

        O ``conversa_id`` é o que liga a consulta ao lead `[S5-24]`, e por isso
        fica fora do ``input_schema``: se fosse argumento, o modelo poderia
        informar o de outra conversa (ou inventar um) e mexer no funil de quem
        não está falando com ele. Vem por injeção, de ``construir_registry``,
        que é chamado uma vez por turno com o valor vindo da sessão.
        """
        self._conversa_id = conversa_id

    def execute(
        self,
        nome: str = "",
        cpf: str = "",
        data_nascimento: str = "",
        telefone: str = "",
        data: Any = "",
        hora: Any = "",
        medico: Any = "",
        email: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """Cria (ou reaproveita) o paciente, agenda a consulta e fecha o lead.

        Raises:
            ToolError: dado faltando ou malformado, horário já ocupado, ou
                falha de escrita. A mensagem é sempre uma frase que o chatbot
                pode dizer ao paciente — nunca id interno nem stacktrace.
        """
        nome = (nome or "").strip()
        telefone = (telefone or "").strip()
        email = (email or "").strip()

        # Ordem deliberada: as checagens baratas e sem banco primeiro, para que
        # um turno com metade dos dados não chegue a tocar em `PACIENTE`.
        if not nome:
            raise ToolError("Falta o nome completo do paciente. Pergunte antes de agendar.")
        if not telefone:
            raise ToolError("Falta o telefone de contato. Pergunte antes de agendar.")
        dia, momento = _horario_valido(data, hora)
        if not validar_cpf(cpf):
            raise ToolError(MSG_CPF_INVALIDO)
        nascimento = _nascimento_valido(data_nascimento)

        # A resolução fica **fora** da transação, como o `slot_id` ficava: quem
        # relê a linha sob lock é o `AgendamentoService`. Perder a corrida entre
        # esta consulta e o lock não é bug — cai na mesma `AgendamentoError` de
        # slot ocupado, e o paciente ouve "esse horário acabou de ser ocupado".
        slot = _resolver_slot(dia, momento, medico)

        try:
            # A transação cobre paciente + consulta + lead. Sem ela, um slot que
            # acabou de ser ocupado deixaria para trás um paciente órfão — alguém
            # que nunca pediu cadastro e que ainda por cima bloquearia o CPF numa
            # segunda tentativa.
            with transaction.atomic():
                paciente = self._paciente(
                    nome=nome,
                    cpf=cpf,
                    nascimento=nascimento,
                    telefone=telefone,
                    email=email,
                )
                consulta = AgendamentoService.agendar(
                    paciente=paciente,
                    slot_id=slot.pk,
                    origem=Consulta.Origem.CHAT,
                )
                self._fechar_lead(consulta, nome=nome, email=email, telefone=telefone)
        except AgendamentoError as exc:
            # As mensagens do service já são escritas para o paciente ouvir (ver
            # a docstring de `apps/agenda/services/agendamento.py`), então elas
            # passam inteiras. O convite no fim é o que faz o modelo oferecer
            # outra data em vez de encerrar o assunto.
            raise ToolError(f"{exc} Quer ver outros horários?") from None
        except IntegrityError:
            # Corrida no cadastro: dois turnos criando o mesmo CPF ao mesmo
            # tempo. Raro, e o `str(exc)` traria nome de constraint.
            logger.warning("IntegrityError ao agendar pelo chat", exc_info=True)
            raise ToolError(MSG_FALHA) from None

        logger.info(
            "Chat agendou a consulta %s no slot %s (conversa %s)",
            consulta.pk,
            slot.pk,
            self._conversa_id,
        )
        return {
            "agendada": True,
            "paciente": paciente.nome,
            "medico": consulta.medico.nome,
            "data": consulta.slot.data.strftime("%d/%m/%Y"),
            "hora": consulta.slot.hora_inicio.strftime("%H:%M"),
            "mensagem": "Consulta confirmada.",
        }

    # -- Internos -----------------------------------------------------------

    @staticmethod
    def _paciente(
        *,
        nome: str,
        cpf: str,
        nascimento: dt.date,
        telefone: str,
        email: str,
    ) -> Paciente:
        """Devolve o paciente daquele CPF, criando-o só se ainda não existir.

        Reaproveitar não é otimização: ``UK_PACIENTE_CPF_HASH`` recusaria o
        segundo cadastro de qualquer forma, e quem já se consultou na clínica
        não pode virar um prontuário paralelo por ter agendado pelo chat.

        O cadastro existente **não** é atualizado com o que o modelo coletou.
        Nome e contato vindos de uma conversa são dado não verificado, e
        sobrescrever o que a recepção conferiu no balcão seria uma regressão
        silenciosa de qualidade de cadastro.
        """
        existente = Paciente.objects.buscar_por_cpf(cpf).first()
        if existente is not None:
            logger.info("Agendamento pelo chat reaproveitou o paciente %s", existente.pk)
            return existente

        paciente = Paciente(
            nome=nome,
            data_nascimento=nascimento,
            telefone=telefone,
            email=email,
        )
        # Nunca atribuir `cpf_cifrado`/`cpf_hash` na mão: as duas colunas são
        # preenchidas juntas aqui, e é isso que impede que fiquem dessincronizadas.
        paciente.definir_cpf(cpf)
        paciente.save()
        return paciente

    def _fechar_lead(
        self,
        consulta: Consulta,
        *,
        nome: str,
        email: str,
        telefone: str,
    ) -> None:
        """Move o lead da conversa para ``AGENDADO``, apontando para a consulta `[S5-24]`.

        É a transição automática do funil: a conversa que virou consulta deixa de
        ser um contato em aberto. Se a conversa ainda não tinha lead (o caminho
        comum hoje, já que ninguém cria lead no meio do diálogo), um é criado já
        na etapa final — o funil precisa registrar a conversão mesmo sem ter
        registrado a chegada.
        """
        if self._conversa_id is None:
            # Sem conversa não há o que procurar: ``conversa_id=None`` casaria
            # com todo lead cadastrado à mão pela recepção, e o primeiro deles
            # seria sequestrado por este agendamento.
            self._criar_lead(consulta, nome=nome, email=email, telefone=telefone)
            return

        # `IDX_LEAD_CONVERSA` existe exatamente para esta pergunta. `-id` porque
        # a mesma conversa poderia ter mais de um lead: o mais recente é o vivo.
        lead = Lead.objects.filter(conversa_id=self._conversa_id).order_by("-id").first()
        if lead is None:
            self._criar_lead(consulta, nome=nome, email=email, telefone=telefone)
            return

        lead.etapa = Lead.Etapa.AGENDADO
        lead.consulta = consulta
        # `atualizado_em` é `auto_now`, mas com `update_fields` o Django só grava
        # as colunas listadas — sem ela o funil mostraria a data da criação.
        campos = ["etapa", "consulta", "atualizado_em"]
        # Só completa o que está em branco. O lead pode ter vindo de um
        # formulário onde a pessoa digitou o próprio contato; o que o modelo
        # transcreveu da conversa não tem por que vencer aquilo.
        if telefone and not lead.telefone:
            lead.telefone = telefone
            campos.append("telefone")
        if email and not lead.email:
            lead.email = email
            campos.append("email")
        lead.save(update_fields=campos)
        logger.info("Lead %s movido para AGENDADO pela consulta %s", lead.pk, consulta.pk)

    def _criar_lead(
        self,
        consulta: Consulta,
        *,
        nome: str,
        email: str,
        telefone: str,
    ) -> Lead:
        return Lead.objects.create(
            nome=nome,
            email=email,
            telefone=telefone,
            conversa_id=self._conversa_id,
            etapa=Lead.Etapa.AGENDADO,
            consulta=consulta,
        )


def _horario_valido(data: Any, hora: Any) -> tuple[dt.date, dt.time]:
    """Parseia o horário escolhido, ou recusa. Não interpreta nada.

    O ponto desta função é o que ela **não** faz: não resolve "amanhã", não
    entende "de manhã", não chuta o ano que falta. Ou vem uma data e uma hora
    escritas nos formatos que ``buscar_slots`` devolve, ou o agendamento não
    acontece — é aqui que "quero quinta às 15h" para.
    """
    return _parseado(data, FORMATOS_DATA).date(), _parseado(hora, FORMATOS_HORA).time()


def _parseado(bruto: Any, formatos: tuple[str, ...]) -> dt.datetime:
    """Primeiro formato de :data:`formatos` que casar com ``bruto``."""
    # `isinstance(bruto, bool)` importa: `True` viraria a string "True" e
    # falharia, mas deixar explícito documenta que booleano não é horário.
    texto = "" if isinstance(bruto, bool) else str(bruto or "").strip().lower()
    for formato in formatos:
        try:
            return dt.datetime.strptime(texto, formato)
        except ValueError:
            continue
    raise ToolError(MSG_HORARIO_ILEGIVEL)


def _resolver_slot(dia: dt.date, momento: dt.time, medico: Any) -> AgendaSlot:
    """Encontra a vaga **livre** daquele dia, hora e médico.

    É o que substituiu o ``slot_id`` como identificador `[S5-12]`, e a garantia
    é a mesma de antes: só existe agendamento se existir linha ``LIVRE`` casando
    exatamente com o que foi pedido. O filtro por ``status`` e por ``ativo`` é o
    que impede agendar horário bloqueado, já tomado ou de médico desligado.

    Raises:
        ToolError: nenhum horário livre naquele instante, médico informado que
            não é um dos livres, ou horário com mais de um médico livre e
            nenhum informado. As três mensagens dizem ao modelo o que perguntar
            em seguida — recusar sem saída faria o turno terminar em desculpa.
    """
    livres = list(
        AgendaSlot.objects.filter(
            status=AgendaSlot.Status.LIVRE,
            data=dia,
            hora_inicio=momento,
            medico__ativo=True,
        )
        .select_related("medico")
        .order_by("medico__nome")
    )
    if not livres:
        raise ToolError(MSG_HORARIO_INDISPONIVEL)

    procurado = _tokens_nome(medico)
    if not procurado:
        if len(livres) == 1:
            # Horário com um único médico livre: não há o que desambiguar, e
            # exigir o nome só para repetir a pergunta atrasaria o paciente.
            return livres[0]
        raise ToolError(_msg_qual_medico(livres))

    # Duas passadas, da comparação mais estrita para a mais frouxa. "Ana Lima"
    # e "Dra. Ana Lima" casam por contenção na primeira; "Dra. Ana" casa por
    # nome compartilhado na segunda. Empate nunca vira escolha: se o nome
    # informado serve para dois médicos livres, o modelo tem que perguntar.
    for candidatos in (
        [s for s in livres if _mesmo_nome(procurado, _tokens_nome(s.medico.nome))],
        [s for s in livres if procurado & _tokens_nome(s.medico.nome)],
    ):
        if len(candidatos) == 1:
            return candidatos[0]
        if len(candidatos) > 1:
            raise ToolError(_msg_qual_medico(candidatos))
    raise ToolError(_msg_outro_medico(livres))


def _tokens_nome(bruto: Any) -> set[str]:
    """Reduz um nome de médico ao que dá para comparar entre duas grafias.

    Minúsculas, sem acento, sem título e sem preposição: ``"Dra. Ana Lima"`` e
    ``"ana lima"`` viram o mesmo conjunto. Comparar por conjunto, e não por
    string, é o que faz "Ana Lima" casar com "Dra. Ana Lima" sem casar "Ana
    Lima" com "Ana Ribeiro" na primeira passada de :func:`_resolver_slot`.
    """
    sem_acento = unicodedata.normalize("NFKD", str(bruto or "")).encode("ascii", "ignore").decode()
    partes = re.split(r"[^a-z]+", sem_acento.lower())
    return {p for p in partes if p and p not in TITULOS_MEDICO and p not in LIGACOES_NOME}


def _mesmo_nome(informado: set[str], real: set[str]) -> bool:
    """Um nome contém o outro — a grafia mais curta ainda identifica a pessoa."""
    return informado <= real or real <= informado


def _nomes_de(slots: list[AgendaSlot]) -> str:
    """Lista de médicos em português, para entrar numa frase de recusa.

    Expor quem está livre não vaza nada: é a mesma informação pública que
    ``buscar_slots`` devolve. O que nunca aparece nas mensagens é id de linha.
    """
    nomes = sorted({s.medico.nome for s in slots})
    if len(nomes) == 1:
        return nomes[0]
    return f"{', '.join(nomes[:-1])} e {nomes[-1]}"


def _msg_qual_medico(slots: list[AgendaSlot]) -> str:
    return (
        f"Nesse horário atendem {_nomes_de(slots)}. Pergunte ao paciente com qual "
        "deles ele prefere ser atendido e agende depois da resposta."
    )


def _msg_outro_medico(slots: list[AgendaSlot]) -> str:
    return (
        f"Esse médico não atende nesse horário. Quem está livre é {_nomes_de(slots)}. "
        "Confirme com o paciente antes de agendar."
    )


def _nascimento_valido(bruto: str) -> dt.date:
    """Parseia a data de nascimento nos formatos de :data:`FORMATOS_DATA`."""
    texto = (bruto or "").strip()
    for formato in FORMATOS_DATA:
        try:
            return dt.datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ToolError(MSG_DATA_INVALIDA)


__all__ = ["CriarLeadEConsultaTool"]

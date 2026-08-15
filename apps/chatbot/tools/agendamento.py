"""A única ferramenta de escrita do chatbot `[S5-12]` `[S5-24]`.

Mora em módulo separado das ferramentas de leitura de propósito. ``consultas.py``
declara na primeira linha que nada ali escreve, e essa invariante vale como
documentação: um erro de interpretação do modelo numa tool de leitura custa uma
resposta ruim; aqui custa um paciente cadastrado e um horário ocupado. Separar
os dois arquivos deixa a superfície de risco visível no ``ls``.

O que impede o modelo de inventar um agendamento
------------------------------------------------
Nada nesta ferramenta aceita horário em texto livre. O único jeito de escolher
uma vaga é o ``slot_id`` que ``buscar_slots`` devolveu — mesmo espírito do
``enum`` de especialidades daquela tool: **restringir o vocabulário no schema é
a defesa mais eficaz contra parâmetro inventado por modelo pequeno**, mais do
que qualquer instrução no prompt. Um "quero quinta às 15h" não tem como virar
consulta sem passar por uma consulta real à agenda.

A escrita em si não acontece aqui: quem cria a ``Consulta`` é o
``AgendamentoService`` `[S3-7]`, com transação e lock. Esta ferramenta traduz —
argumentos do modelo viram objetos de domínio, exceções de domínio viram frases
que o chatbot consegue falar.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from django.db import IntegrityError, transaction

from apps.agenda.models import Consulta
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

MSG_SLOT_INVALIDO = (
    "Antes de agendar, mostre os horários disponíveis e peça para o paciente escolher um deles."
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
    # gravar". As duas frases sobre `slot_id` e sobre dado faltando existem para
    # impedir uso prematuro — o erro clássico é chamar com os campos em branco
    # logo depois de o paciente dizer "quero marcar".
    description = (
        "Agenda a consulta de verdade. É a única ferramenta que grava algo, "
        "então use apenas no final: quando o paciente JÁ escolheu um dos "
        "horários que buscar_slots mostrou e JÁ informou nome, CPF, data de "
        "nascimento e telefone. O slot_id precisa ser exatamente um dos "
        "devolvidos por buscar_slots — nunca invente esse número nem agende um "
        "horário que você não mostrou. Se faltar algum dado, ou se o paciente "
        "ainda não escolheu o horário, não chame esta ferramenta: pergunte."
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
            "slot_id": {
                "type": "integer",
                "description": (
                    "Número do horário escolhido, copiado do campo slot_id que "
                    "buscar_slots devolveu. Não aceita data nem hora em texto."
                ),
            },
            "email": {
                "type": "string",
                "description": "E-mail do paciente, se ele informar. Opcional.",
            },
        },
        "required": ["nome", "cpf", "data_nascimento", "telefone", "slot_id"],
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
        slot_id: Any = None,
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
        slot = _slot_id_valido(slot_id)
        if not validar_cpf(cpf):
            raise ToolError(MSG_CPF_INVALIDO)
        nascimento = _nascimento_valido(data_nascimento)

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
                    slot_id=slot,
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
            slot,
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


def _slot_id_valido(bruto: Any) -> int:
    """Converte o ``slot_id`` recebido do modelo em inteiro, ou recusa.

    O ponto desta função é o que ela **não** faz: não interpreta "quinta às
    15h", não procura por data e hora, não tenta ser prestativa. Ou o valor é o
    número que ``buscar_slots`` devolveu, ou o agendamento não acontece.
    """
    # `bool` é subclasse de `int`: sem esta linha, `slot_id=True` viraria o
    # slot 1 — um horário real, de um paciente real.
    if bruto is None or isinstance(bruto, bool):
        raise ToolError(MSG_SLOT_INVALIDO)
    try:
        return int(str(bruto).strip())
    except (TypeError, ValueError):
        raise ToolError(MSG_SLOT_INVALIDO) from None


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

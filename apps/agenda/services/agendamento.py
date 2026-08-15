"""Agendamento de uma consulta em um slot — o caminho único de escrita.

Toda consulta do ClinicOS nasce aqui: recepção `[S3-13]`, chatbot `[S5-12]` e
site chamam :meth:`AgendamentoService.agendar`, e ninguém instancia
:class:`~apps.agenda.models.Consulta` à mão. O motivo é a invariante que o banco
não impõe: ``consulta.medico`` é cópia de ``slot.medico`` (desnormalização
deliberada — ver a docstring do model), e cópia só é confiável quando existe
**um** lugar que a preenche.

Onde mora a integridade
-----------------------
No schema, não neste módulo. São duas constraints, em camadas distintas:

- ``UK_SLOT_MEDICO_HORARIO``, em ``AGENDA_SLOT`` — não existem dois slots no
  mesmo (médico, data, hora de início);
- o ``UNIQUE`` do ``OneToOneField`` ``Consulta.slot`` — não existem duas
  consultas no mesmo slot.

A segunda é a que protege *este* fluxo. Um ``INSERT`` disparado por outro
processo, por um script de carga ou por um bug futuro continua sendo recusado
pelo banco sem passar por aqui — é isso que torna a garantia verificável.

O que a transação acrescenta é **qualidade de experiência**, não a garantia: o
``SELECT ... FOR UPDATE`` serializa os pedidos concorrentes pelo mesmo horário
para que o segundo receba "esse horário não está mais disponível" em vez de um
erro de banco. Se ela falhar, a resposta continua correta — só fica feia. Daí
``IntegrityError`` virar a mesma exceção do slot já ocupado: para quem chama,
perder a corrida e chegar atrasado são o mesmo evento.

Por que ``FOR UPDATE`` e não ``ISOLATION LEVEL SERIALIZABLE``
------------------------------------------------------------
A ``ARQUITETURA.md`` pede "transação serializável"; o efeito prático vem do
lock de linha sob o ``READ COMMITTED`` que é o default do Oracle e do Django.
Serializável de verdade responderia ``ORA-08177`` ("cannot serialize access")
na colisão, e caberia ao chamador reexecutar o turno inteiro — política de
retry que nem a recepção nem o chatbot têm. Com ``FOR UPDATE`` a segunda
transação apenas espera; liberado o lock, o Oracle refaz a leitura sob o novo
snapshot e ela enxerga o slot já ``RESERVADO``, caindo na checagem de status.

Na suíte padrão (SQLite) ``select_for_update()`` é *no-op*: o backend não
suporta o lock e o Django omite a cláusula em silêncio, sem erro. Os testes de
``test_agendamento.py`` seguem valendo porque verificam o contrato — exceção,
estado final, ausência de lixo. O lock só existe no Oracle, e é lá que
``test_agendamento_oracle.py`` `[S3-6]` `[S3-8]` prova o schema segurando.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agenda.models import AgendaSlot, Consulta

if TYPE_CHECKING:
    from apps.crm.models import Paciente

logger = logging.getLogger(__name__)

# Mensagens de erro são parte da interface: o chatbot verbaliza ``str(exc)``
# direto para o paciente `[S5-12]`. Nada de id interno, nome de constraint ou
# detalhe de conexão — só o que a recepção diria ao telefone.
MSG_INDISPONIVEL = "Esse horário não está mais disponível. Por favor, escolha outro."
MSG_PASSADO = "Esse horário já passou. Escolha uma data a partir de hoje."


class AgendamentoError(Exception):
    """Falha de regra de negócio ao agendar.

    Base comum para quem só quer saber se deu certo. Toda subclasse carrega uma
    mensagem pronta para ser exibida ao paciente — ver o comentário das
    constantes acima.
    """


class SlotIndisponivelError(AgendamentoError):
    """O horário não pode ser ocupado: tomado, bloqueado ou inexistente.

    Os casos viram deliberadamente a mesma exceção. Para quem pede o
    agendamento não há diferença prática entre "outra pessoa marcou primeiro",
    "a recepção bloqueou a tarde" e "esse slot não existe"; e responder o último
    em voz alta entregaria a existência (ou não) de linhas do banco a quem só
    mandou um número.
    """


class SlotNoPassadoError(SlotIndisponivelError):
    """A data do slot é anterior a hoje.

    Subclasse — e não irmã — de :class:`SlotIndisponivelError`: quem só precisa
    saber que o horário não serve continua com um ``except`` só, e quem quiser
    explicar melhor ("esse horário já passou") tem o caso separado.
    """


class AgendamentoService:
    """Cria consultas. Ponto de entrada único de escrita em ``CONSULTA``."""

    @staticmethod
    def agendar(
        *,
        paciente: Paciente,
        slot_id: int,
        origem: str,
        observacoes: str = "",
    ) -> Consulta:
        """Ocupa um slot livre e devolve a consulta criada.

        Args:
            paciente: Quem será atendido.
            slot_id: PK do slot escolhido. É o id, e não a instância, porque a
                linha precisa ser relida **sob lock** dentro da transação: um
                objeto carregado antes da chamada já está desatualizado por
                definição, e é exatamente essa defasagem que produz overbooking.
            origem: Por onde o agendamento entrou — um valor de
                ``Consulta.Origem``. Obrigatório e sem default: é o denominador
                da métrica de conversão do chatbot `[S5-28]`, e default silencioso
                contaminaria a medição.
            observacoes: Anotação operacional curta da recepção.

        Returns:
            A ``Consulta`` criada, com ``status`` ``AGENDADA`` e ``medico`` já
            preenchido a partir do slot.

        Raises:
            SlotNoPassadoError: a data do slot é anterior a hoje.
            SlotIndisponivelError: o slot não existe, não está ``LIVRE``, ou foi
                ocupado por outra transação no meio do caminho.

        Note:
            **Não recebe ``medico`` — e não deve receber.** ``Consulta.medico``
            é cópia de ``slot.medico``, e a assinatura omite o parâmetro de
            propósito: se o caller pudesse informá-lo, a invariante dependeria
            de todo caller acertar, e o banco não a verifica.
        """
        with transaction.atomic():
            try:
                # Trava a linha até o fim da transação. Quem chegar depois fica
                # esperando aqui, e não na constraint.
                slot = AgendaSlot.objects.select_for_update().get(pk=slot_id)
            except AgendaSlot.DoesNotExist:
                # `from None`: ``DoesNotExist`` é vocabulário do ORM e não pode
                # vazar para a view nem para a tool do chatbot.
                raise SlotIndisponivelError(MSG_INDISPONIVEL) from None

            if slot.status != AgendaSlot.Status.LIVRE:
                raise SlotIndisponivelError(MSG_INDISPONIVEL)

            # Comparação por data, não por horário: recusar "hoje às 9h às
            # 9h05" exigiria uma política de antecedência mínima, que é decisão
            # de produto e ainda não existe. A data já cobre o caso real —
            # agenda antiga que continua no banco por retenção.
            if slot.data < timezone.localdate():
                raise SlotNoPassadoError(MSG_PASSADO)

            try:
                consulta = Consulta.objects.create(
                    paciente=paciente,
                    slot=slot,
                    # `medico_id` (e não `medico`) evita uma query por
                    # agendamento. Puxar o objeto via `select_related` no
                    # `select_for_update` seria pior: o Oracle travaria também a
                    # linha do médico, serializando agendamentos de horários
                    # diferentes do mesmo profissional.
                    medico_id=slot.medico_id,
                    origem=origem,
                    observacoes=observacoes,
                )
            except IntegrityError:
                # A corrida que passou pela checagem de status e bateu no UNIQUE
                # do OneToOne — a rede que o schema estende sob esta transação.
                #
                # O `except` é largo de propósito (distinguir ORA-00001 de
                # ORA-01400 exigiria ler a mensagem do driver, que muda entre
                # backends). O `exc_info` compensa: se um dia um IntegrityError
                # de outra natureza cair aqui, o traceback aparece no log em vez
                # de sumir dentro de "horário indisponível".
                #
                # WARNING, e não ERROR: perder a corrida é desfecho de negócio
                # normal sob concorrência, e o volume disto é justamente a
                # medida de contenção da agenda.
                logger.warning("IntegrityError ao agendar no slot %s", slot_id, exc_info=True)
                raise SlotIndisponivelError(MSG_INDISPONIVEL) from None

            slot.status = AgendaSlot.Status.RESERVADO
            slot.save(update_fields=["status"])

        logger.info(
            "Consulta %s criada no slot %s (origem=%s)", consulta.pk, slot_id, consulta.origem
        )
        return consulta

"""Ferramentas de leitura do chatbot.

Todas consultam o banco e **nenhuma escreve**. Criar lead ou consulta fica
para uma entrega posterior (S5-12) — o que reduz bastante a superfície de risco
desta primeira versão: um erro de interpretação do modelo custa uma resposta
ruim, nunca um agendamento fantasma.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.utils import timezone

from apps.agenda.models import AgendaSlot
from apps.chatbot.models import FaqVector
from apps.chatbot.repositories.faq import FAQRepository, VetorIncompativelError
from apps.chatbot.services.embeddings import get_embedding_provider
from apps.crm.models import Especialidade

from .base import BaseTool, ToolError

logger = logging.getLogger(__name__)

# Teto de itens devolvidos ao modelo. Contexto é caro (4096 tokens no Ollama) e
# lista longa aumenta a chance de o modelo transcrever errado na resposta.
MAX_SLOTS = 5
MAX_FAQS = 3

# Acima desta distância de cosseno, o resultado é ruído. Sem corte, a busca
# vetorial sempre devolve "o menos distante", mesmo para pergunta fora de
# assunto — e o modelo trata isso como resposta válida.
DISTANCIA_MAXIMA_FAQ = 0.85

PERIODOS = {
    "manha": (dt.time(0, 0), dt.time(12, 0)),
    "tarde": (dt.time(12, 0), dt.time(18, 0)),
    "noite": (dt.time(18, 0), dt.time(23, 59, 59)),
}


class ListarEspecialidadesTool(BaseTool):
    """Lista as especialidades ativas da clínica."""

    name = "listar_especialidades_disponiveis"
    description = (
        "Lista as especialidades médicas atendidas pela clínica. Use quando o "
        "paciente perguntar o que a clínica atende, ou quando não estiver claro "
        "qual especialidade ele precisa."
    )
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        especialidades = Especialidade.objects.filter(ativo=True).order_by("nome")
        return {
            "especialidades": [{"nome": e.nome, "descricao": e.descricao} for e in especialidades]
        }


class BuscarSlotsTool(BaseTool):
    """Busca horários livres de uma especialidade."""

    name = "buscar_slots"
    description = (
        "Busca horários disponíveis para uma especialidade. Use SEMPRE que o "
        "paciente perguntar sobre horário, agenda, vaga ou disponibilidade. "
        "Retorna lista vazia quando não há horário livre."
    )

    def __init__(self, especialidades: list[str] | None = None) -> None:
        """Monta o schema com o ``enum`` das especialidades reais.

        Restringir o vocabulário no próprio schema é a defesa mais eficaz
        contra parâmetro inventado por um modelo pequeno — mais do que qualquer
        instrução no prompt. Sem o ``enum``, "quero um cardiologista" vira
        ``especialidade="Cardiologia"`` e a busca devolve vazio sem explicar
        que a clínica sequer atende isso.
        """
        if especialidades is None:
            especialidades = list(
                Especialidade.objects.filter(ativo=True)
                .order_by("nome")
                .values_list("nome", flat=True)
            )
        self._especialidades = especialidades
        propriedades: dict[str, Any] = {
            "especialidade": {
                "type": "string",
                "description": "Nome da especialidade médica.",
            },
            "periodo_preferido": {
                "type": "string",
                "enum": list(PERIODOS),
                "description": "Período do dia preferido pelo paciente. Opcional.",
            },
        }
        if especialidades:
            propriedades["especialidade"]["enum"] = especialidades
        self.input_schema = {
            "type": "object",
            "properties": propriedades,
            "required": ["especialidade"],
        }

    def execute(self, especialidade: str = "", periodo_preferido: str = "", **_: Any) -> dict:
        if not especialidade:
            raise ToolError("Informe a especialidade desejada.")

        # Match tolerante: o modelo às vezes manda "Oftalmologia Pediátrica"
        # quando o cadastro é "Oftalmologia Pediatrica", ou só "Retina".
        obj = (
            Especialidade.objects.filter(ativo=True, nome__iexact=especialidade).first()
            or Especialidade.objects.filter(ativo=True, nome__icontains=especialidade).first()
        )
        if obj is None:
            return {
                "encontrada": False,
                "mensagem": f"A clínica não atende '{especialidade}'.",
                "especialidades_atendidas": self._especialidades,
                "slots": [],
            }

        qs = AgendaSlot.objects.filter(
            status=AgendaSlot.Status.LIVRE,
            data__gte=timezone.localdate(),
            medico__ativo=True,
            medico__especialidades=obj,
        ).select_related("medico")

        faixa = PERIODOS.get((periodo_preferido or "").lower())
        if faixa:
            qs = qs.filter(hora_inicio__gte=faixa[0], hora_inicio__lt=faixa[1])

        slots = qs.order_by("data", "hora_inicio")[:MAX_SLOTS]
        return {
            "encontrada": True,
            "especialidade": obj.nome,
            "slots": [
                {
                    "slot_id": s.pk,
                    "medico": s.medico.nome,
                    "data": s.data.strftime("%d/%m/%Y"),
                    "hora": s.hora_inicio.strftime("%H:%M"),
                }
                for s in slots
            ],
        }


class BuscarFaqTool(BaseTool):
    """Busca semântica na FAQ da clínica, via Oracle AI Vector Search."""

    name = "buscar_faq"
    description = (
        "Consulta a base de perguntas frequentes da clínica. Use para dúvidas "
        "sobre convênios, preços, formas de pagamento, endereço, estacionamento, "
        "preparo para a consulta, exames e sintomas. NÃO use para horários."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pergunta": {
                "type": "string",
                "description": "A pergunta do paciente, com as palavras dele.",
            }
        },
        "required": ["pergunta"],
    }

    def execute(self, pergunta: str = "", **_: Any) -> dict[str, Any]:
        if not pergunta.strip():
            raise ToolError("Informe a pergunta do paciente.")

        try:
            embedding = get_embedding_provider().gerar([pergunta])[0]
            resultados = FAQRepository.buscar_semantica(embedding, top_k=MAX_FAQS)
        except VetorIncompativelError:
            # Base indexada com outro modelo. Melhor admitir do que devolver
            # ranking errado — o Oracle não acusaria nada.
            logger.exception("FAQ indexada com dimensão diferente da configurada")
            raise ToolError("A base de perguntas está sendo atualizada.") from None
        except Exception:  # noqa: BLE001
            logger.exception("Falha na busca semântica de FAQ")
            raise ToolError("Não consegui consultar a base de perguntas agora.") from None

        relevantes = [(i, d) for i, d in resultados if d <= DISTANCIA_MAXIMA_FAQ]
        if not relevantes:
            return {"encontrou": False, "resultados": []}

        # Hidrata pelo ORM: evita ler RESPOSTA (NCLOB) pelo cursor cru, onde o
        # driver devolveria um objeto LOB em vez de str.
        por_id = {f.pk: f for f in FaqVector.objects.filter(pk__in=[i for i, _ in relevantes])}
        return {
            "encontrou": True,
            "resultados": [
                {
                    "faq_id": faq_id,
                    "pergunta": por_id[faq_id].pergunta,
                    "resposta": por_id[faq_id].resposta,
                    "distancia": round(dist, 4),
                }
                for faq_id, dist in relevantes
                if faq_id in por_id
            ],
        }


def construir_registry():
    """Monta o registry do turno com as três ferramentas de leitura.

    Import tardio para evitar ciclo: ``tools`` importa models, e o registry é
    consumido pelo ``ChatService``.
    """
    from .base import ToolRegistry

    return ToolRegistry([ListarEspecialidadesTool(), BuscarSlotsTool(), BuscarFaqTool()])


__all__ = [
    "BuscarFaqTool",
    "BuscarSlotsTool",
    "ListarEspecialidadesTool",
    "construir_registry",
]

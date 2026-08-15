"""Views do chat público.

O turno é dividido em dois requests, e isso é intencional:

``POST /chat/mensagem/``
    Registra a pergunta e devolve o fragmento HTML da conversa. Barato,
    idempotente do ponto de vista do modelo, e é onde a sessão é gravada.

``GET /chat/stream/<uuid>/``
    Abre o SSE e roda o turno.

Por que não um request só
-------------------------
Duas razões, ambas por causa de como o ``EventSource`` se comporta:

1. **Ele reconecta sozinho.** Se o gerador terminar sem ``event: close``, ou
   der erro, o browser refaz o GET em ~3 s. Com um request único isso
   reexecutaria a inferência inteira, saturando o Ollama — que atende um
   pedido por vez. Com a mensagem já persistida, a view detecta que aquele
   turno já foi respondido e encerra na hora.
2. **``EventSource`` só faz GET.** Mandar a pergunta na query string
   funcionaria (foi o que o spike fez), mas coloca texto do paciente em log de
   servidor e histórico do browser.

Sessão e streaming não se misturam
----------------------------------
``SessionMiddleware.process_response`` roda **antes** de o gerador ser
consumido, então qualquer escrita em ``request.session`` dentro do stream é
silenciosamente perdida. Por isso o ``conversa_id`` é gravado no POST, e o
histórico vive em ``InteracaoChat``, não na sessão.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.chatbot import sse
from apps.chatbot.models import InteracaoChat
from apps.chatbot.services.chat import ChatService
from apps.chatbot.tools import construir_registry

logger = logging.getLogger(__name__)

CHAVE_SESSAO = "chat_conversa_id"
LIMITE_PERGUNTA = 500


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """Página do chat."""
    return render(request, "chatbot/chat.html")


@require_POST
def mensagem(request: HttpRequest) -> HttpResponse:
    """Recebe a pergunta e devolve o par de balões (pergunta + destino da resposta).

    O ``conversa_id`` nasce aqui e vai para a sessão — é o que amarra os turnos
    e o que a view de stream usa para autorizar o acesso.
    """
    pergunta = (request.POST.get("pergunta") or "").strip()[:LIMITE_PERGUNTA]
    if not pergunta:
        return HttpResponse(status=204)

    conversa_id = request.session.get(CHAVE_SESSAO)
    if not conversa_id:
        conversa_id = str(uuid.uuid4())
        request.session[CHAVE_SESSAO] = conversa_id

    sequencia = InteracaoChat.objects.filter(conversa_id=conversa_id).count() + 1

    return render(
        request,
        "chatbot/_turno.html",
        {
            "pergunta": pergunta,
            "conversa_id": conversa_id,
            "sequencia": sequencia,
            "url_stream": f"/chat/stream/{conversa_id}/?s={sequencia}",
        },
    )


@require_GET
def stream(request: HttpRequest, conversa_id: uuid.UUID) -> StreamingHttpResponse:
    """Executa o turno e transmite a resposta por SSE.

    Raises:
        Http404: se a conversa não for a da sessão. Sem essa checagem, quem
            adivinhasse um UUID leria a conversa alheia.
    """
    if str(conversa_id) != request.session.get(CHAVE_SESSAO):
        raise Http404("Conversa não encontrada.")

    pergunta = (request.GET.get("q") or "").strip()[:LIMITE_PERGUNTA]
    try:
        sequencia = int(request.GET.get("s", "1"))
    except ValueError:
        sequencia = 1

    resposta = StreamingHttpResponse(
        _eventos(conversa_id, sequencia, pergunta),
        content_type="text/event-stream",
    )
    resposta["Cache-Control"] = "no-cache"
    # Sem isto o nginx bufferiza o corpo inteiro e nada aparece até o fim.
    resposta["X-Accel-Buffering"] = "no"
    return resposta


def _eventos(conversa_id: uuid.UUID, sequencia: int, pergunta: str):
    """Gera os eventos do turno, cobrindo o caso de reconexão do EventSource."""
    if not pergunta:
        yield sse.erro("Não recebi sua pergunta. Tente enviar de novo.")
        yield sse.fechar()
        return

    # Reconexão: este turno já foi respondido. Encerrar de imediato evita
    # reexecutar a inferência e duplicar a linha de auditoria.
    ja_respondido = InteracaoChat.objects.filter(
        conversa_id=conversa_id, sequencia=sequencia
    ).first()
    if ja_respondido is not None:
        logger.info("Reconexão no turno %s/%s — reemitindo", conversa_id, sequencia)
        if ja_respondido.resposta:
            yield sse.token(ja_respondido.resposta)
        yield sse.fechar()
        return

    historico = _historico(conversa_id)
    # O registry é montado aqui porque é aqui que o ``conversa_id`` já foi
    # autorizado contra a sessão. A ferramenta de agendamento precisa dele para
    # achar o lead da conversa `[S5-24]`, e ele **não pode** vir do modelo: como
    # argumento de tool, uma alucinação (ou uma injeção no texto do paciente)
    # mexeria no funil de outra pessoa.
    yield from ChatService(registry=construir_registry(conversa_id=conversa_id)).responder(
        pergunta=pergunta,
        conversa_id=conversa_id,
        historico=historico,
        sequencia=sequencia,
    )


def _historico(conversa_id: uuid.UUID) -> list[dict[str, str]]:
    """Turnos anteriores, no formato de mensagens do protocolo.

    Limitado por ``CHAT_HISTORICO_MAX_TURNOS``: o contexto real do Ollama é
    4096 tokens e o excedente é descartado em silêncio — inclusive o system
    prompt com os guardrails, que fica no começo.
    """
    anteriores = InteracaoChat.objects.filter(conversa_id=conversa_id).order_by("-sequencia")[
        : settings.CHAT_HISTORICO_MAX_TURNOS
    ]
    mensagens: list[dict[str, str]] = []
    for turno in reversed(list(anteriores)):
        mensagens.append({"role": "user", "content": turno.pergunta})
        if turno.resposta:
            mensagens.append({"role": "assistant", "content": turno.resposta})
    return mensagens

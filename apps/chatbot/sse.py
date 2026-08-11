"""Framing de Server-Sent Events para o chat.

Só formatação — nenhuma regra de negócio. Isolar aqui permite testar o
protocolo sem subir LLM nem banco, e é onde estão os detalhes que quebram em
produção de forma silenciosa.

Contrato dos eventos
--------------------
======== =================================== ==============================
evento   quando                              o que a UI faz
======== =================================== ==============================
status   antes e durante o trabalho pesado   troca a linha de status
token    cada fragmento da resposta          acrescenta ao balão
fontes   FAQs que embasaram a resposta       mostra as citações
erro     falha em qualquer ponto             mostra aviso, encerra
close    sempre, no ``finally``              fecha a conexão
======== =================================== ==============================

Três decisões que vieram de defeitos observados no spike:

**1. O payload é escapado.** A extensão SSE do htmx injeta o conteúdo como
HTML. Como o texto vem de um LLM que recebe entrada do usuário, mandá-lo cru é
XSS por prompt injection (``<img onerror=...>``). Escapar por fragmento é
seguro: ``"<scr"`` vira ``&lt;scr`` e nunca se recompõe em tag.

**2. Quebra de linha vira múltiplas linhas ``data:``.** É o que o protocolo
manda, e o cliente reconcatena com ``\\n``. O spike trocava ``\\n`` por espaço,
o que destruía a formatação da resposta.

**3. Erro não vaza detalhe técnico.** O spike mandava ``str(exc)`` para o
browser, expondo DSN, usuário do Oracle e caminho de arquivo. Aqui só entra
mensagem escrita para o paciente ler.
"""

from __future__ import annotations

from django.utils.html import escape

# Comentário SSE (linha iniciada por ``:``). O cliente ignora, mas o byte
# trafega — é o que mantém viva uma conexão ociosa atrás de proxy e o que faz
# o browser assumir a conexão como aberta já no primeiro instante.
KEEPALIVE = ": keepalive\n\n"


def evento(nome: str, dados: str, *, escapar: bool = True) -> str:
    """Formata um evento SSE.

    Args:
        nome: Nome do evento (``status``, ``token``, ``erro``, ``close``...).
        dados: Payload. Quebras de linha viram múltiplas linhas ``data:``.
        escapar: Se ``True`` (padrão), escapa HTML. Passe ``False`` **somente**
            para markup gerado pelo servidor, nunca para saída de LLM.

    Returns:
        Bloco pronto para o ``StreamingHttpResponse``.
    """
    payload = escape(dados) if escapar else dados
    # `\r\n` primeiro, senão o `\r` sobra e vira uma linha `data:` fantasma.
    linhas = payload.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    corpo = "\n".join(f"data: {linha}" for linha in linhas)
    return f"event: {nome}\n{corpo}\n\n"


def status(mensagem: str) -> str:
    """Evento de status — o que o usuário vê enquanto espera."""
    return evento("status", mensagem)


def token(fragmento: str) -> str:
    """Um pedaço da resposta do modelo. Sempre escapado."""
    return evento("token", fragmento)


def erro(mensagem: str) -> str:
    """Falha, com mensagem já pensada para o paciente ler."""
    return evento("erro", mensagem)


def fechar() -> str:
    """Encerra o stream.

    Precisa ser emitido **sempre**, num ``finally``. Sem ele o ``EventSource``
    do browser interpreta o fim como queda e **refaz o request em ~3 s** — o
    que reexecuta o turno inteiro e satura o Ollama, que atende um pedido por
    vez.
    """
    return evento("close", "fim")

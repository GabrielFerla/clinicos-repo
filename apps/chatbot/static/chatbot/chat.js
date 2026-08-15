/**
 * Conversa do assistente da clínica — POST do turno + streaming por SSE.
 *
 * Extraído do `chat.html` na [S4-7], quando a landing ganhou o painel
 * flutuante: a página `/chat/` e o widget da landing rodam exatamente o mesmo
 * fluxo, e mantê-lo em dois lugares garantiria que divergissem. O script se
 * liga a todo elemento `[data-chat]` do documento, então os dois podem
 * inclusive coexistir na mesma página.
 *
 * Continua com `EventSource` puro, sem a extensão SSE do htmx. As três razões
 * originais seguem valendo:
 *
 *   1. Zero dependência de CDN. O README do spike registra que rede corporativa
 *      bloqueia unpkg/jsdelivr, e um chat que não carrega na rede do cliente
 *      piloto não serve.
 *   2. O contrato de eventos é tipado (`status`, `token`, `erro`, `close`) e
 *      cada um faz coisa diferente com o DOM — trocar conteúdo, acrescentar,
 *      encerrar. Expressar isso com `sse-swap` exigiria um alvo por evento.
 *   3. Segurança: usando `textContent` o texto do modelo nunca é interpretado
 *      como HTML. A extensão do htmx injeta como HTML, o que transforma prompt
 *      injection em XSS. O servidor já escapa (ver `apps/chatbot/sse.py`); isto
 *      é a segunda camada.
 *
 * Isso não conflita com o ADR-0003: o que ele rejeita é SPA/Vue. E o ADR-0005
 * reserva explicitamente o chat como caso de UI custom.
 *
 * Contrato do markup — a raiz `[data-chat]` precisa de:
 *
 *   data-chat                     marca a raiz
 *   data-url-mensagem="/chat/…"   endpoint do POST do turno
 *   data-autofocus                opcional: foca o campo já na carga (a página
 *                                 usa; o painel flutuante não, senão rouba o
 *                                 foco e rola a landing sozinha)
 *
 * e conter `[data-conversa]`, `[data-formulario]`, `[data-campo]`,
 * `[data-enviar]`. O `[data-formulario]` precisa do `{% csrf_token %}`.
 */
(() => {
  "use strict";

  const iniciar = (raiz) => {
    const conversa = raiz.querySelector("[data-conversa]");
    const formulario = raiz.querySelector("[data-formulario]");
    const campo = raiz.querySelector("[data-campo]");
    const botao = raiz.querySelector("[data-enviar]");
    const urlMensagem = raiz.dataset.urlMensagem;

    if (!conversa || !formulario || !campo || !botao || !urlMensagem) {
      // Markup incompleto: melhor não ligar nada do que ligar pela metade.
      return;
    }

    const entradaCsrf = formulario.querySelector("[name=csrfmiddlewaretoken]");
    const csrf = entradaCsrf ? entradaCsrf.value : "";

    const rolar = () => {
      conversa.scrollTop = conversa.scrollHeight;
    };

    const travar = (travado) => {
      botao.disabled = travado;
      campo.disabled = travado;
      if (!travado) campo.focus();
    };

    // As sugestões prontas do painel são só atalhos para o mesmo envio.
    raiz.querySelectorAll("[data-sugestao]").forEach((atalho) => {
      atalho.addEventListener("click", () => {
        if (campo.disabled) return;
        campo.value = atalho.dataset.sugestao || atalho.textContent.trim();
        formulario.requestSubmit();
      });
    });

    formulario.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const pergunta = campo.value.trim();
      if (!pergunta) return;

      travar(true);
      campo.value = "";

      let bloco;
      try {
        const resposta = await fetch(urlMensagem, {
          method: "POST",
          headers: { "X-CSRFToken": csrf, "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ pergunta }),
        });
        if (!resposta.ok) throw new Error("falha ao registrar a mensagem");
        const molde = document.createElement("div");
        molde.innerHTML = await resposta.text();
        bloco = molde.firstElementChild;
        conversa.appendChild(bloco);
        rolar();
      } catch {
        travar(false);
        return;
      }

      const status = bloco.querySelector("[data-status]");
      const alvo = bloco.querySelector("[data-resposta]");
      const aviso = bloco.querySelector("[data-erro]");

      // A pergunta vai na query string do GET porque EventSource só faz GET. Ela
      // já foi validada e truncada no POST; aqui serve para o turno ser
      // reexecutável de forma idempotente (o servidor detecta turno já
      // respondido e encerra sem chamar o modelo de novo).
      const url = bloco.dataset.stream + "&q=" + encodeURIComponent(bloco.dataset.pergunta);
      const fonte = new EventSource(url);

      const encerrar = () => {
        fonte.close();
        travar(false);
      };

      fonte.addEventListener("status", (e) => {
        // Payload vazio significa "apague o indicador".
        if (e.data) {
          status.textContent = e.data;
          status.hidden = false;
        } else {
          status.hidden = true;
        }
        rolar();
      });

      // textContent, nunca innerHTML: o texto vem de um LLM que recebeu entrada
      // do usuário. O servidor já escapa; esta é a segunda camada.
      fonte.addEventListener("token", (e) => {
        alvo.textContent += e.data;
        rolar();
      });

      fonte.addEventListener("erro", (e) => {
        status.hidden = true;
        aviso.textContent = e.data;
        aviso.hidden = false;
        rolar();
      });

      fonte.addEventListener("close", () => {
        status.hidden = true;
        encerrar();
      });

      // Falha de rede. Sem fechar aqui, o EventSource reconecta a cada ~3s e
      // reexecuta o turno, saturando o Ollama (que atende um pedido por vez).
      fonte.onerror = () => {
        if (!alvo.textContent) {
          aviso.textContent = "Conexão interrompida. Tente enviar de novo.";
          aviso.hidden = false;
        }
        status.hidden = true;
        encerrar();
      };
    });

    if (raiz.hasAttribute("data-autofocus")) campo.focus();
  };

  document.querySelectorAll("[data-chat]").forEach(iniciar);
})();

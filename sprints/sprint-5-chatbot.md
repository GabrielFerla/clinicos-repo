# Sprint 5 — Chatbot inteligente com agendamento

**Duração:** 2 semanas
**Período:** Semanas 10-11
**Status:** 🔄 Em andamento — 16/33 · o chat agenda de verdade desde 14/08; faltam anti-abuso, notificações e testes adversariais

## Meta

> Paciente conversa com o chatbot no site e agenda consulta sozinho, com dados grounded no Oracle. Funil de leads do CRM operando.

---

## Tarefas

### Componente de chat no site
- [x] **S5-1** Componente HTMX de chat com streaming via SSE · **FRONT** · 8h
- [x] **S5-2** Estado da conversa persistido em sessão (não perde se recarregar) · **FRONT+BACK** · 4h
- [x] **S5-3** Indicador "digitando" enquanto LLM processa · **FRONT** · 2h
- [ ] **S5-4** Animação suave de aparição dos tokens · **FRONT** · 2h
- [ ] **S5-5** Botão "Falar com atendente" como fallback humano · **FRONT** · 2h

### ChatService e arquitetura
- [x] **S5-6** Service Django `ChatService` orquestrando turnos da conversa · **BACK+AI** · 8h
- [x] **S5-7** Prompt de sistema com persona da clínica e guardrails · **AI** · 6h
- [ ] **S5-8** Mecanismo de retry e fallback se Claude API falhar · **BACK+AI** · 4h

### Tools (cada uma é uma classe com schema + execute)
- [x] **S5-9** Tool: `listar_especialidades_disponiveis()` · **AI** · 2h
- [x] **S5-10** Tool: `buscar_slots(especialidade, periodo_preferido)` · **AI** · 4h
- [ ] **S5-11** Tool: `triagem_oftalmologica(sintomas)` — sugere especialidade · **AI** · 5h
- [x] **S5-12** Tool: `criar_lead_e_consulta(dados_paciente, slot_id)` · **AI+BACK** · 6h
- [x] **S5-13** Tool: `buscar_faq(pergunta)` usando `VECTOR_DISTANCE` no Oracle · **AI+DB** · 5h
- [ ] **S5-14** Tool: `cancelar_consulta_recente(email, telefone)` (limitado a 1h após criar) · **AI+BACK** · 4h

### Ingestão de FAQ e Vector Search
- [x] **S5-15** Pipeline de ingestão: ler FAQ do site → gerar embeddings → popular `FAQ_VECTOR` · **AI** · 5h
- [x] **S5-16** Command Django `reindexar_faq` para reprocessar quando FAQ mudar · **AI+BACK** · 3h
- [x] **S5-17** Testes de relevância da busca semântica (10 queries de baseline) · **QA+AI** · 4h

### Anti-abuso
- [ ] **S5-18** Rate limiting por IP no endpoint do chat · **BACK** · 3h
- [ ] **S5-19** Honeypot anti-spam no formulário inicial · **BACK** · 2h
- [ ] **S5-20** Validação de e-mail (regex + double opt-in opcional) · **BACK** · 3h
- [ ] **S5-21** Detecção de palavras-chave de abuso e bloqueio automático · **BACK** · 2h

### CRM (funil de leads)
- [ ] **S5-22** Model `Lead` com etapas: novo → qualificado → agendado → compareceu → retorno · **BACK** · 3h
- [x] **S5-23** Admin para visualizar funil e mover leads entre etapas · **BACK+FRONT** · 5h
- [x] **S5-24** Transição automática de Lead → Consulta quando chat agenda · **BACK** · 3h
- [ ] **S5-25** Dashboard simples no Admin com contagem por etapa · **FRONT** · 4h

### Auditoria e custos
- [x] **S5-26** Model `InteracaoChat` registrando cada turno + tokens + custo estimado · **BACK** · 3h
- [x] **S5-27** View de auditoria de conversas no Admin (somente leitura) · **FRONT+BACK** · 3h
- [ ] **S5-28** Métrica custom: custo médio por agendamento · **BACK** · 2h

### Notificações
- [ ] **S5-29** E-mail de confirmação de consulta (template HTML + texto) · **BACK+DESIGN** · 4h
- [ ] **S5-30** E-mail de lembrete D-1 (Celery Beat) · **BACK** · 3h

### Testes
- [ ] **S5-31** Testes E2E do fluxo: chat → agendamento → e-mail recebido · **QA** · 6h
- [ ] **S5-32** Testes adversariais: prompt injection, sycophancy, alucinação · **QA+AI** · 5h
- [ ] **S5-33** Teste de relevância: chatbot recusa "me dá uma receita" claramente · **QA+AI** · 2h

---

## Definition of Done

- [x] Paciente fictício consegue agendar consulta sem nenhuma intervenção humana
- [ ] Chatbot recusa pedidos fora do escopo (ex: receita médica) com mensagem clara e empática
- [ ] Tentativa de prompt injection no campo de sintoma é tratada sem comprometer o sistema
- [ ] Custo médio por agendamento registrado e ≤ R$ 0,50 em tokens
- [ ] FAQ Vector Search retorna respostas relevantes em ≤ 300ms
- [ ] Médico abre painel e vê a consulta criada pelo chatbot com queixa pré-preenchida
- [x] Funil do CRM mostra leads em diferentes etapas
- [ ] E-mail de confirmação chega corretamente formatado
- [ ] Rate limit funciona: 100 tentativas seguidas do mesmo IP = bloqueio

---

## Demos da review

> **Esta é a apresentação mais importante do projeto.** Reservar tempo extra de preparo.

1. **Paciente real** (cliente piloto convidado) tenta agendar via chatbot, sem instrução prévia
2. **Médico** abre painel e mostra a consulta com queixa pré-preenchida
3. **Vector Search ao vivo**: paciente pergunta "quanto custa" → chatbot responde com info de convênio
4. **Teste adversarial ao vivo**: alguém da banca tenta prompt injection, vê funcionar a defesa
5. **Funil do CRM**: mostrar lead novo → qualificado → agendado em tempo real

---

## Notas

**14/08/2026 — fatia "mini CRM + chat que agenda".** O chat deixou de ser só de leitura.
Ver `docs/STATUS.md` e `docs/CHAT_MVP.md`.

- **A tool de escrita mora em `apps/chatbot/tools/agendamento.py`**, separada do
  `consultas.py` — aquele módulo declara na primeira linha que nada ali escreve, e essa
  invariante vale como documentação. O `construir_registry()` subiu para
  `tools/__init__.py`, já que montar o conjunto deixou de ser assunto de um módulo só.
- **A vaga é identificada por data, hora e médico** — quem traduz isso em PK é o
  servidor, filtrando por `status=LIVRE`. Data e hora passam só nos formatos fixos, então
  "quinta às 15h" continua não virando consulta. Era `slot_id` cru até 19/08 (ver a nota
  daquele dia).
- **O `conversa_id` não passa pelo modelo.** Ele é injetado em `construir_registry()`
  pela view, *depois* de o UUID já ter sido conferido contra a sessão. O modelo não tem
  como forjar de qual conversa é o lead que está sendo fechado.
- **Paciente é reaproveitado por `cpf_hash`**, nunca duplicado; e `SlotIndisponivelError`
  vira mensagem verbalizável ("esse horário acabou de ser ocupado, quer ver outros?").
- **O DoD "paciente fictício agenda sem intervenção humana" está fechado**, verificado com
  LLM real (`qwen2.5:14b`) contra o Oracle: 4 turnos, do "queria marcar retina" até a
  consulta gravada com `origem=CHAT`, slot `RESERVADO`, paciente com CPF cifrado e lead
  em `AGENDADO`. Três observações dessa rodada:
  - **O número de turnos varia.** Às vezes o modelo agenda no 3º turno; às vezes pede uma
    confirmação extra antes de chamar a tool. É o comportamento que o prompt pede, mas
    significa que teste E2E com roteiro fixo é flaky por natureza — a S5-31 precisa
    asseverar o estado final no banco, não a contagem de turnos.
  - **`detectar_alucinacao` dá falso positivo em toda confirmação** — ver débito #16 do
    `STATUS.md`. Corrompe o sinal que a S5-32 e o risco R4 usam.
  - **O modelo expõe `slot_id` ao paciente** ("08:00 com a Dra. Ana Lima (slot_id 2241)").
    Não é falha de segurança, mas é id interno vazando na conversa. Resolvido em 19/08 —
    ver a nota daquele dia.
**19/08/2026 — o `slot_id` saiu da conversa `[S5-12]`.** O relato foi a resposta abaixo,
com o número grudado no nome do médico e um pedido para o paciente informar o id:

```
- 08:00 com Dr. Bruno Carvalho31)
- 08:00 com Dra. Ana Lima327)
Qual horário você prefere? Por favor, escolha um dos horários listados e informe o
slot_id correspondente.
```

Duas causas, uma de cada natureza:

- **A tool pedia o id, então o modelo pedia o id.** `criar_lead_e_consulta` tinha
  `slot_id` obrigatório no schema e `buscar_slots` devolvia o campo. Um dado que está no
  contexto entra na conversa de alguma forma — filtrar a saída não conserta isso. Agora a
  vaga é escolhida por `data`, `hora` e `medico`, e o servidor resolve para a PK numa
  consulta restrita a `LIVRE` (`_resolver_slot`). O nome do médico casa por conjunto de
  tokens, sem título nem acento, e **empate vira pergunta**: dois médicos livres no mesmo
  horário com o nome informado ambíguo devolvem "com qual deles?" em vez de escolher.
- **O filtro de streaming vazava o resto do número.** `_FiltroSlotId` removia a menção
  no fragmento em que o primeiro dígito chegava, e os dígitos seguintes já não casavam
  com nada — daí o `31)` solto na tela. A remoção agora só roda no trecho que não pode
  mais crescer. O filtro fica como rede de segunda linha (o modelo pode inventar a
  menção sozinho), não como defesa principal.

Verificado com `qwen2.5:14b` real: listagem sem número nenhum ao lado dos nomes, e os
4 turnos do "quero marcar" até a consulta gravada com o médico e a hora certos.

- **Fora do escopo desta fatia:** S5-4/S5-5, S5-8, S5-11 (triagem), S5-14 (cancelamento),
  S5-18 a S5-21 (anti-abuso), S5-25 (dashboard), S5-28 (custo), S5-29/S5-30 (e-mails),
  S5-31 a S5-33 (E2E e adversariais).

---

## Riscos específicos desta sprint

- **R4** (alucinação) — esta é A sprint para provar grounding. Testes adversariais são DoD, não opcional
- **R6** (prompt injection) — mesmo
- **R7** (custo) — monitoramento de custo precisa começar aqui, não depois do go-live

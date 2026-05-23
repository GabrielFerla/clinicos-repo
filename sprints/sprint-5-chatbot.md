# Sprint 5 — Chatbot inteligente com agendamento

**Duração:** 2 semanas
**Período:** Semanas 10-11
**Status:** ☐ Pendente

## Meta

> Paciente conversa com o chatbot no site e agenda consulta sozinho, com dados grounded no Oracle. Funil de leads do CRM operando.

---

## Tarefas

### Componente de chat no site
- [ ] **S5-1** Componente HTMX de chat com streaming via SSE · **FRONT** · 8h
- [ ] **S5-2** Estado da conversa persistido em sessão (não perde se recarregar) · **FRONT+BACK** · 4h
- [ ] **S5-3** Indicador "digitando" enquanto LLM processa · **FRONT** · 2h
- [ ] **S5-4** Animação suave de aparição dos tokens · **FRONT** · 2h
- [ ] **S5-5** Botão "Falar com atendente" como fallback humano · **FRONT** · 2h

### ChatService e arquitetura
- [ ] **S5-6** Service Django `ChatService` orquestrando turnos da conversa · **BACK+AI** · 8h
- [ ] **S5-7** Prompt de sistema com persona da clínica e guardrails · **AI** · 6h
- [ ] **S5-8** Mecanismo de retry e fallback se Claude API falhar · **BACK+AI** · 4h

### Tools (cada uma é uma classe com schema + execute)
- [ ] **S5-9** Tool: `listar_especialidades_disponiveis()` · **AI** · 2h
- [ ] **S5-10** Tool: `buscar_slots(especialidade, periodo_preferido)` · **AI** · 4h
- [ ] **S5-11** Tool: `triagem_oftalmologica(sintomas)` — sugere especialidade · **AI** · 5h
- [ ] **S5-12** Tool: `criar_lead_e_consulta(dados_paciente, slot_id)` · **AI+BACK** · 6h
- [ ] **S5-13** Tool: `buscar_faq(pergunta)` usando `VECTOR_DISTANCE` no Oracle · **AI+DB** · 5h
- [ ] **S5-14** Tool: `cancelar_consulta_recente(email, telefone)` (limitado a 1h após criar) · **AI+BACK** · 4h

### Ingestão de FAQ e Vector Search
- [ ] **S5-15** Pipeline de ingestão: ler FAQ do site → gerar embeddings → popular `FAQ_VECTOR` · **AI** · 5h
- [ ] **S5-16** Command Django `reindexar_faq` para reprocessar quando FAQ mudar · **AI+BACK** · 3h
- [ ] **S5-17** Testes de relevância da busca semântica (10 queries de baseline) · **QA+AI** · 4h

### Anti-abuso
- [ ] **S5-18** Rate limiting por IP no endpoint do chat · **BACK** · 3h
- [ ] **S5-19** Honeypot anti-spam no formulário inicial · **BACK** · 2h
- [ ] **S5-20** Validação de e-mail (regex + double opt-in opcional) · **BACK** · 3h
- [ ] **S5-21** Detecção de palavras-chave de abuso e bloqueio automático · **BACK** · 2h

### CRM (funil de leads)
- [ ] **S5-22** Model `Lead` com etapas: novo → qualificado → agendado → compareceu → retorno · **BACK** · 3h
- [ ] **S5-23** Admin para visualizar funil e mover leads entre etapas · **BACK+FRONT** · 5h
- [ ] **S5-24** Transição automática de Lead → Consulta quando chat agenda · **BACK** · 3h
- [ ] **S5-25** Dashboard simples no Admin com contagem por etapa · **FRONT** · 4h

### Auditoria e custos
- [ ] **S5-26** Model `InteracaoChat` registrando cada turno + tokens + custo estimado · **BACK** · 3h
- [ ] **S5-27** View de auditoria de conversas no Admin (somente leitura) · **FRONT+BACK** · 3h
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

- [ ] Paciente fictício consegue agendar consulta sem nenhuma intervenção humana
- [ ] Chatbot recusa pedidos fora do escopo (ex: receita médica) com mensagem clara e empática
- [ ] Tentativa de prompt injection no campo de sintoma é tratada sem comprometer o sistema
- [ ] Custo médio por agendamento registrado e ≤ R$ 0,50 em tokens
- [ ] FAQ Vector Search retorna respostas relevantes em ≤ 300ms
- [ ] Médico abre painel e vê a consulta criada pelo chatbot com queixa pré-preenchida
- [ ] Funil do CRM mostra leads em diferentes etapas
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

_(adicionar durante a execução)_

---

## Riscos específicos desta sprint

- **R4** (alucinação) — esta é A sprint para provar grounding. Testes adversariais são DoD, não opcional
- **R6** (prompt injection) — mesmo
- **R7** (custo) — monitoramento de custo precisa começar aqui, não depois do go-live

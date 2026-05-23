# Sprint 3 — Agenda e disponibilidade

**Duração:** 2 semanas
**Período:** Semanas 6-7
**Status:** ☐ Pendente

## Meta

> Recepção define agenda semanal por médico; sistema gera slots automaticamente; agendamentos não fazem overbooking sob nenhuma circunstância.

---

## Tarefas

### Modelos e lógica
- [ ] **S3-1** Refinar model `AgendaRegra`: dia da semana + horário início/fim + duração da consulta + intervalo · **BACK** · 4h
- [ ] **S3-2** Suporte a exceções: feriado, congresso, plantão (bloqueio manual) · **BACK** · 5h

### Geração de slots
- [ ] **S3-3** Command Django `gerar_slots --dias 60` · **BACK** · 5h
- [ ] **S3-4** Job Celery agendado (Celery Beat) gerando slots diariamente · **BACK** · 4h
- [ ] **S3-5** Tratamento de bordas: o que fazer se regra mudou no meio · **BACK** · 3h

### Anti-overbooking
- [ ] **S3-6** Confirmar constraint UNIQUE no Oracle + tratamento de IntegrityError · **DB+BACK** · 3h
- [ ] **S3-7** Service `AgendamentoService.agendar` com transação serializável · **BACK** · 5h
- [ ] **S3-8** Testes de concorrência: dois agendamentos no mesmo slot devem falhar · **QA** · 4h
- [ ] **S3-9** Teste de carga simples (Locust) para 100 agendamentos simultâneos · **QA** · 5h

### Interfaces
- [ ] **S3-10** Tela de gestão de agenda no Admin com componentes visuais · **BACK+FRONT** · 8h
- [ ] **S3-11** Calendário visual de slots por médico (Alpine.js + HTMX) · **FRONT** · 10h
- [ ] **S3-12** Tela "Minha agenda" do médico com filtros por data e status · **BACK+FRONT** · 6h
- [ ] **S3-13** Tela de bloqueio manual de slots para recepção · **BACK+FRONT** · 5h

### Endpoint para o chatbot
- [ ] **S3-14** Endpoint interno `consultar_slots(especialidade, data_range)` retornando JSON · **BACK** · 4h
- [ ] **S3-15** Testes do endpoint cobrindo casos vazios, lotados, com bloqueio · **QA** · 3h

### Notificações iniciais
- [ ] **S3-16** Template de e-mail "Consulta agendada com sucesso" · **BACK+DESIGN** · 3h
- [ ] **S3-17** Envio via Celery após criação de consulta · **BACK** · 2h

---

## Definition of Done

- [ ] Recepção cria regra de agenda semanal e visualiza slots gerados nos próximos 60 dias
- [ ] Dois processos simultâneos tentando agendar o mesmo slot: apenas um sucesso, outro recebe mensagem clara
- [ ] Médico abre "Minha agenda" e vê suas consultas do dia ordenadas
- [ ] Recepção bloqueia slot manualmente e ele some das opções disponíveis
- [ ] Endpoint `consultar_slots` retorna JSON pronto para consumo pelo chatbot
- [ ] Teste de carga (100 requests simultâneas) passa sem deadlocks no Oracle
- [ ] E-mail de confirmação chega no Mailhog após agendamento

---

## Demos da review

1. **Recepção define agenda** — cria regra "Dr. Fulano, segunda a sexta, 8h-12h, consultas de 30min" e vê 200 slots gerados
2. **Médico vê sua agenda** — fluxo completo, com filtros
3. **Bloqueio manual** — recepção bloqueia tarde de quarta para congresso, slots somem
4. **Teste de concorrência ao vivo** — script disparando 10 requests simultâneas no mesmo slot, apenas 1 vira consulta

---

## Notas

_(adicionar durante a execução)_

---

## Riscos específicos desta sprint

- **R5** (overbooking) — esta é A sprint onde isso tem que ser provado. Sem teste de carga, sem DoD
- **R8** (scope creep) — cliente vai querer "agenda em formato Google Calendar". Postergar

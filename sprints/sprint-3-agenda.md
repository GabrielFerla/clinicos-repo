# Sprint 3 — Agenda e disponibilidade

**Duração:** 2 semanas
**Período:** Semanas 6-7
**Status:** 🔄 Em andamento — 4/17 · geração de slots e anti-overbooking entregues na fatia de 14/08; faltam exceções, telas e notificações

## Meta

> Recepção define agenda semanal por médico; sistema gera slots automaticamente; agendamentos não fazem overbooking sob nenhuma circunstância.

---

## Tarefas

### Modelos e lógica
- [ ] **S3-1** Refinar model `AgendaRegra`: dia da semana + horário início/fim + duração da consulta + intervalo · **BACK** · 4h
- [ ] **S3-2** Suporte a exceções: feriado, congresso, plantão (bloqueio manual) · **BACK** · 5h

### Geração de slots
- [x] **S3-3** Command Django `gerar_slots --dias 60` · **BACK** · 5h
- [ ] **S3-4** Job Celery agendado (Celery Beat) gerando slots diariamente · **BACK** · 4h
- [ ] **S3-5** Tratamento de bordas: o que fazer se regra mudou no meio · **BACK** · 3h

### Anti-overbooking
- [x] **S3-6** Confirmar constraint UNIQUE no Oracle + tratamento de IntegrityError · **DB+BACK** · 3h
- [x] **S3-7** Service `AgendamentoService.agendar` com transação serializável · **BACK** · 5h
- [x] **S3-8** Testes de concorrência: dois agendamentos no mesmo slot devem falhar · **QA** · 4h
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
- [x] Dois processos simultâneos tentando agendar o mesmo slot: apenas um sucesso, outro recebe mensagem clara
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

**14/08/2026 — fatia "mini CRM + chat que agenda".** S3-3, S3-6, S3-7 e S3-8 saíram fora
da ordem da sprint, porque a S5-12 (agendar pelo chat) depende delas. Ver `docs/STATUS.md`.

- **`bulk_create(ignore_conflicts=True)` não funciona no Oracle.** O backend do Django
  declara `supports_ignore_conflicts = False` e a flag levanta `NotSupportedError` — a
  suíte ficaria verde no SQLite com o comando quebrado em produção. O `gerar_slots`
  condiciona a flag a `connection.features` e, no caminho Oracle, refaz o lote linha a
  linha em savepoints quando bate `IntegrityError`. **Vale para a S3-4** (Celery Beat),
  que vai reusar esse command.
- **`select_for_update()` é no-op silencioso no SQLite.** Por isso os testes de corrida
  de verdade estão em `apps/agenda/test_agendamento_oracle.py`, marcados
  `@pytest.mark.oracle` — o lock real e o `ORA-00001` só existem no Oracle.
- **S3-6 confirmada no banco**, via `USER_CONSTRAINTS`: `UK_SLOT_MEDICO_HORARIO` e o
  UNIQUE do `OneToOneField` de `Consulta.slot` (nome autogerado). São as duas camadas
  descritas na docstring do model.
- **`AgendamentoService.agendar` é keyword-only e não aceita `medico`** — ele deriva de
  `slot.medico`, mantendo a invariante `consulta.medico == slot.medico` que o banco não
  impõe. O `ConsultaAdmin` também passa por ele, senão a recepção criaria consulta
  deixando o slot `LIVRE` e o chatbot seguiria oferecendo aquele horário.
- **S3-10 ficou parcial e segue aberta:** `AgendaRegra` e `Consulta` agora têm tela no
  Admin com filtros e busca, mas sem os "componentes visuais" que a tarefa pede.
- **Fora do escopo desta fatia:** S3-1, S3-2, S3-4, S3-5, S3-9 (Locust), S3-11 a S3-15,
  S3-16/S3-17 (e-mails).

---

## Riscos específicos desta sprint

- **R5** (overbooking) — esta é A sprint onde isso tem que ser provado. Sem teste de carga, sem DoD
- **R8** (scope creep) — cliente vai querer "agenda em formato Google Calendar". Postergar

# Sprints — Visão geral

Cada arquivo nesta pasta representa uma sprint do MVP1. As tarefas têm IDs no formato `S{sprint}-{numero}` (ex: `S2-5`) e devem ser marcadas como concluídas conforme avançam.

## Cadência

| Cerimônia | Quando | Duração | Quem |
|---|---|---|---|
| Planning | Primeiro dia da sprint | 1h | Dev lead + cliente piloto (review do escopo) |
| Daily (opcional) | Diariamente | 10min | Solo: bullet rápido em notas pessoais |
| Review | Último dia da sprint | 1h | Dev lead + cliente piloto |
| Retrospectiva | Após review | 30min | Solo: o que funcionou / o que melhorar |

## Como ler um arquivo de sprint

Cada sprint tem:

1. **Meta** — uma frase que descreve o resultado esperado
2. **Tarefas** — lista com checkbox, código, descrição, responsável e estimativa
3. **Definition of Done** — critérios verificáveis de conclusão
4. **Demos** — o que mostrar ao cliente na review
5. **Notas** — observações livres durante a execução

## Status global do MVP1

| Sprint | Período | Status | Notas |
|---|---|---|---|
| [Sprint 0 — Validação técnica](sprint-0-validacao.md) | Semana 1 | 🔄 26/27 | Falta só apresentar a spike (S0-27) |
| [Sprint 1 — Fundação](sprint-1-fundacao.md) | Semanas 2-3 | 🔄 20/26 | Trilha técnica concluída; faltam design, cliente e processo |
| [Sprint 2 — CRM interno](sprint-2-crm.md) | Semanas 4-5 | ☐ Pendente | — |
| [Sprint 3 — Agenda](sprint-3-agenda.md) | Semanas 6-7 | ☐ Pendente | — |
| [Sprint 4 — Site público](sprint-4-site.md) | Semanas 8-9 | ☐ Pendente | — |
| [Sprint 5 — Chatbot inteligente](sprint-5-chatbot.md) | Semanas 10-11 | 🔄 12/33 | Fatia vertical do chat de leitura entregue fora de ordem (ver `docs/CHAT_MVP.md`) |
| [Sprint 6 — Atendimento + hardening](sprint-6-prontuario.md) | Semanas 12-13 | ☐ Pendente | — |

## Legenda de responsáveis

| Sigla | Significado |
|---|---|
| BACK | Backend (Python/Django) |
| FRONT | Frontend (Templates/HTMX/Tailwind) |
| DB | Banco de dados (Oracle, SQL, PL/SQL) |
| DEVOPS | Infraestrutura, Docker, CI/CD |
| DESIGN | UI/UX |
| AI | Integração com IA, prompts, tool use |
| QA | Testes |
| TODOS | Toda a equipe / decisão coletiva |

# Plano de Ação — ClinicOS MVP1

> Documento mestre do projeto. Vive aqui, evolui com o projeto. O PDF formal é gerado a partir deste e dos demais arquivos de `docs/` ao final de cada sprint.

**Status:** versão 1.0 · Maio de 2026 · Em planejamento
**Cliente piloto:** clínica de oftalmologia
**Duração planejada:** 13 semanas (1 + 6×2)

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Personas no MVP1](#2-personas-no-mvp1)
3. [Resumo do escopo](#3-resumo-do-escopo) — detalhes em [`ESCOPO.md`](ESCOPO.md)
4. [Resumo da arquitetura](#4-resumo-da-arquitetura) — detalhes em [`ARQUITETURA.md`](ARQUITETURA.md)
5. [Sprints](#5-sprints) — detalhes em [`sprints/`](../sprints/)
6. [Riscos](#6-riscos) — detalhes em [`RISCOS.md`](RISCOS.md)
7. [Métricas](#7-métricas) — detalhes em [`METRICAS.md`](METRICAS.md)
8. [Próximos passos](#8-próximos-passos)

---

## 1. Visão geral

O ClinicOS valida em sua primeira entrega o fluxo central de valor de uma clínica privada:

> **Paciente conversa com chatbot no site → agenda consulta → médico recebe o atendimento já organizado em seu painel.**

A escolha por **oftalmologia** como cliente piloto é estratégica:

- Subespecialidades bem definidas (refrativa, catarata, retina, glaucoma, lentes de contato, pediátrica, plástica ocular)
- Alto índice de retorno do paciente — excelente vitrine para CRM e fidelização
- Exames diagnósticos como parte central do fluxo — diferencia o ClinicOS de soluções genéricas

### Princípios de design

- **Validar antes de escalar** — Sprint 0 de POC técnica antes de tocar no produto real
- **Conformidade desde o dia 1** — LGPD e normas do CFM não são entregas de v2
- **Prontuário append-only** — imutabilidade garantida no banco, não só na aplicação
- **Oracle 23ai como plataforma** — Vector Search, JSON, criptografia nativa. Não tratamos Oracle como SQL genérico
- **Cortar escopo, não qualidade** — escopo enxuto, bem feito, com testes
- **Chatbot grounded** — todo dado vem de query real via Tool Use. LLM nunca inventa horários, médicos ou especialidades

---

## 2. Personas no MVP1

| Persona | Acessa o sistema? | Responsabilidades |
|---|---|---|
| **Paciente** | Não loga | Conversa com chatbot no site, agenda consulta, recebe confirmação por e-mail |
| **Médico oftalmologista** | Sim | Visualiza agenda do dia, atende paciente, registra evolução, consulta histórico |
| **Recepção / Admin** | Sim | Cadastra médicos e pacientes, gerencia agenda, realiza agendamentos manuais |

> **Decisão de escopo:** paciente não loga no sistema no MVP1. Confirmação de agendamento via e-mail. Reduz ~30% da complexidade de autenticação, recuperação de senha e tratamento LGPD nesta primeira entrega.

---

## 3. Resumo do escopo

**Dentro do MVP1 (14 funcionalidades):** site institucional, chatbot inteligente com agendamento, catálogo de especialidades, cadastros (médicos, pacientes), agenda recorrente, prontuário append-only, histórico do paciente, funil de leads, Vector Search no FAQ, log LGPD, e-mail transacional.

**Fora do MVP1 (vai para MVP2 ou v3):** telemedicina, prescrição eletrônica, TISS/TUSS, WhatsApp/SMS, ICP-Brasil, MFA, mobile, dashboards financeiros, integração com equipamentos diagnósticos, faturamento, multi-clínica.

→ Lista completa e detalhada em [`ESCOPO.md`](ESCOPO.md).

---

## 4. Resumo da arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│                     PACIENTE (não loga)                       │
│                          ↓                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  SITE PÚBLICO (Django Templates + Tailwind + HTMX)   │    │
│  │   ↓                                                  │    │
│  │   CHATBOT (HTMX + SSE streaming)                     │    │
│  │     ↓                                                │    │
│  │     ChatService → Claude API com Tool Use            │    │
│  └──────────────────────────────────────────────────────┘    │
│                          ↓                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  TOOLS (executadas server-side, grounded no Oracle)  │    │
│  │  • listar_especialidades()                           │    │
│  │  • buscar_slots(especialidade, periodo)              │    │
│  │  • triagem_oftalmologica(sintomas)                   │    │
│  │  • criar_lead_e_consulta(...)                        │    │
│  │  • buscar_faq(pergunta)  ← Vector Search 23ai        │    │
│  └──────────────────────────────────────────────────────┘    │
│                          ↓                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  ORACLE DATABASE 23ai                                │    │
│  │  • Tabelas relacionais clássicas                     │    │
│  │  • Coluna VECTOR para FAQ semântica                  │    │
│  │  • Triggers de imutabilidade em EVOLUCAO             │    │
│  │  • CPF criptografado + hash determinístico           │    │
│  └──────────────────────────────────────────────────────┘    │
│                          ↑                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  CRM INTERNO (Django Admin + django-unfold)          │    │
│  │  Recepção e médico logam aqui                        │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

**Stack consolidada:** Django 5 · Oracle 23ai · python-oracledb (thin) · django-unfold · HTMX · Alpine.js · Tailwind · Anthropic SDK · Celery + Redis · Docker Compose · OCI.

→ Detalhes completos em [`ARQUITETURA.md`](ARQUITETURA.md).

---

## 5. Sprints

| # | Sprint | Duração | Meta | Arquivo |
|---|---|---|---|---|
| 0 | Validação técnica | 1 semana | Provar a stack ponta a ponta antes do produto real | [sprint-0-validacao.md](../sprints/sprint-0-validacao.md) |
| 1 | Fundação | 2 semanas | Ambiente real, schema completo, equipe alinhada | [sprint-1-fundacao.md](../sprints/sprint-1-fundacao.md) |
| 2 | CRM interno | 2 semanas | Recepção loga e cadastra com qualidade de SaaS moderno | [sprint-2-crm.md](../sprints/sprint-2-crm.md) |
| 3 | Agenda | 2 semanas | Slots gerados automaticamente, anti-overbooking | [sprint-3-agenda.md](../sprints/sprint-3-agenda.md) |
| 4 | Site público | 2 semanas | Site da clínica bonito, rápido, responsivo | [sprint-4-site.md](../sprints/sprint-4-site.md) |
| 5 | Chatbot inteligente | 2 semanas | Paciente agenda sozinho via chat grounded no Oracle | [sprint-5-chatbot.md](../sprints/sprint-5-chatbot.md) |
| 6 | Atendimento + hardening | 2 semanas | Prontuário válido + sistema em produção monitorado | [sprint-6-prontuario.md](../sprints/sprint-6-prontuario.md) |

---

## 6. Riscos

12 riscos identificados, com destaque para:

- **Crítico:** LGPD inadequada na entrega final
- **Alto:** fricção do driver Oracle, chatbot alucinar, scope creep, backup nunca testado em restore
- **Médio:** overbooking, prompt injection, custo de API, resistência dos médicos
- **Baixo:** banca não valorizar features modernas da Oracle

→ Detalhes e mitigações em [`RISCOS.md`](RISCOS.md).

---

## 7. Métricas

O MVP1 é considerado bem-sucedido quando, nos primeiros 30 dias após o go-live:

- ≥ 40% dos agendamentos vêm pelo chatbot
- Tempo médio de agendamento via chat ≤ 3 minutos
- ≥ 90% das consultas atendidas têm evolução registrada
- Tempo médio para registrar evolução ≤ 5 minutos
- Custo de IA por agendamento ≤ R$ 0,50
- Uptime ≥ 99,5%

→ Lista completa em [`METRICAS.md`](METRICAS.md).

---

## 8. Próximos passos

### Decisões pendentes antes da Sprint 0

- [ ] Confirmar formalmente clínica piloto de oftalmologia (qual, com quantos médicos, qual perfil)
- [ ] Validar disponibilidade do domínio `clinicos.com.br` ou variante
- [ ] Decidir tier OCI (Always Free vs créditos do patrocínio)
- [ ] Definir provedor de e-mail transacional (Resend, AWS SES, Mailgun)
- [ ] Alinhar com cliente piloto a lista de "fora do escopo" por escrito
- [ ] Definir SLA de uptime e tempo de resposta (para dimensionar infra)
- [ ] Definir orçamento mensal para APIs (Claude, embeddings, e-mail)

### Após validação deste documento

- [ ] Criar issues no GitHub a partir das tarefas das sprints
- [ ] Definir milestones por sprint
- [ ] Estimativa em pontos por tarefa (se houver time)
- [ ] Reunião de kickoff com cliente piloto + assinatura de escopo
- [ ] Início da Sprint 0

---

## Histórico de versões

| Versão | Data | Mudanças |
|---|---|---|
| 1.0 | 2026-05-17 | Versão inicial do plano. Aprovação interna pendente. |

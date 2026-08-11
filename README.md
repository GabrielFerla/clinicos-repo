# ClinicOS

[![CI](https://github.com/GabrielFerla/clinicos-repo/actions/workflows/ci.yml/badge.svg)](https://github.com/GabrielFerla/clinicos-repo/actions/workflows/ci.yml)

> Sistema de gestão para clínicas médicas privadas brasileiras, com foco no fluxo central de valor: paciente conversa com chatbot no site, agenda consulta e o médico recebe o atendimento já organizado em seu painel interno.

**Cliente piloto MVP1:** clínica de oftalmologia.
**Patrocínio acadêmico:** Oracle (uso pleno do ecossistema 23ai).

---

## Stack principal

| Camada | Tecnologia |
|---|---|
| Banco de dados | Oracle Database 23ai Free (AI Vector Search, JSON Duality) |
| Backend + CRM interno | Django 5 + Python 3.12 |
| Driver Oracle | `python-oracledb` (thin mode) |
| Tema do Admin | django-unfold (visual moderno baseado em Tailwind) |
| Site público | Django Templates + Tailwind CSS |
| Interatividade | HTMX + Alpine.js (sem SPA, sem Vue) |
| Chatbot | Anthropic Python SDK com Tool Use + streaming SSE |
| Tarefas async | Celery + Redis |
| Container | Docker Compose |
| CI / CD | GitHub Actions |
| Deploy | OCI Compute / Container Instances |

---

## Como navegar este repositório

Esta é a **fase de planejamento** do ClinicOS. Aqui você encontra a documentação viva do projeto, decisões arquiteturais registradas e o plano de execução por sprint. O código da aplicação começa na Sprint 1 e será adicionado em apps Django separados conforme as sprints avançam.

```
clinicos/
├── README.md                  ← você está aqui
├── CONTRIBUTING.md            ← como trabalhar neste repositório
├── docs/
│   ├── STATUS.md             ← o que existe de fato no código, hoje (vivo)
│   ├── PLANO.md              ← documento mestre do projeto (vivo)
│   ├── ESCOPO.md             ← escopo do MVP1 + lista de fora-de-escopo
│   ├── ARQUITETURA.md        ← detalhes técnicos, modelo de dados, decisões
│   ├── CHAT_MVP.md           ← guia de implementação do chatbot (fatia vertical)
│   ├── METRICAS.md           ← métricas de sucesso e como medi-las
│   ├── RISCOS.md             ← registro vivo de riscos do projeto
│   └── adr/                  ← Architecture Decision Records
│       ├── README.md         ← índice dos ADRs
│       ├── 0001-banco-oracle-23ai.md
│       ├── 0002-django-em-vez-de-laravel.md
│       ├── 0003-htmx-sem-vue.md
│       └── 0004-provedor-embeddings.md
└── sprints/
    ├── README.md             ← visão geral e cadência das sprints
    ├── sprint-0-validacao.md
    ├── sprint-1-fundacao.md
    ├── sprint-2-crm.md
    ├── sprint-3-agenda.md
    ├── sprint-4-site.md
    ├── sprint-5-chatbot.md
    └── sprint-6-prontuario.md
```

---

## Setup local em 1 comando

```bash
make setup
```

Sobe Oracle 23ai + Redis + Mailhog + Django, aplica migrations e cria superuser `admin/admin`. Pré-requisitos: Docker + Docker Compose v2 (não precisa de Python no host). Detalhes, tempo estimado e troubleshooting em [`docs/SETUP.md`](docs/SETUP.md).

---

## Onde começar

**Se você está chegando agora ao projeto:**

1. Leia este README até o fim
2. Leia [`docs/STATUS.md`](docs/STATUS.md) — **o que já existe no código e o que ainda não roda**
3. Leia [`docs/PLANO.md`](docs/PLANO.md) — visão completa
4. Leia [`docs/adr/`](docs/adr/) — entenda as decisões tomadas
5. Leia [`sprints/sprint-0-validacao.md`](sprints/sprint-0-validacao.md) — primeiro trabalho prático

**Se você é o cliente piloto:**

1. Leia [`docs/ESCOPO.md`](docs/ESCOPO.md) — o que está e o que não está no MVP1
2. Leia [`docs/METRICAS.md`](docs/METRICAS.md) — como vamos medir sucesso

**Se você é a banca / patrocinador:**

1. Leia [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — decisões técnicas e uso do Oracle 23ai
2. Leia todos os ADRs em [`docs/adr/`](docs/adr/) — raciocínio por trás de cada escolha

---

## Cronograma

| Bloco | Duração | Período | Status |
|---|---|---|---|
| Sprint 0 — Validação técnica | 1 semana | Semana 1 | ☐ Pendente |
| Sprint 1 — Fundação | 2 semanas | Semanas 2-3 | ☐ Pendente |
| Sprint 2 — CRM interno | 2 semanas | Semanas 4-5 | ☐ Pendente |
| Sprint 3 — Agenda | 2 semanas | Semanas 6-7 | ☐ Pendente |
| Sprint 4 — Site público | 2 semanas | Semanas 8-9 | ☐ Pendente |
| Sprint 5 — Chatbot inteligente | 2 semanas | Semanas 10-11 | ☐ Pendente |
| Sprint 6 — Atendimento + hardening | 2 semanas | Semanas 12-13 | ☐ Pendente |

**Total: 13 semanas.**

---

## Princípios de design

- **Validar antes de escalar** — Sprint 0 de POC técnica antes de tocar no produto real
- **Conformidade desde o dia 1** — LGPD e normas do CFM não são entregas de v2
- **Prontuário append-only** — imutabilidade garantida no banco, não só na aplicação
- **Oracle 23ai como plataforma** — Vector Search, JSON, criptografia nativa
- **Cortar escopo, não qualidade** — escopo enxuto, bem feito, com testes
- **Chatbot grounded** — todo dado vem de query real via Tool Use. LLM nunca inventa horários, médicos ou especialidades

---

## Licença

Projeto acadêmico. Licenciamento comercial a definir após validação do MVP1 com o cliente piloto.

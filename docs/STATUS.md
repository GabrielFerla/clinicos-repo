# Status do Projeto — ClinicOS MVP1

> Documento vivo, escrito para o time técnico. Snapshot do que **existe de fato no código** — não do que está planejado. Regenerar ao fim de cada sprint. Para o plano, ver [`PLANO.md`](PLANO.md); para o escopo, [`ESCOPO.md`](ESCOPO.md); para as tarefas, [`sprints/`](../sprints/).

**Snapshot:** 11/08/2026 · branch `feature/s5-chat-mvp` · última atividade de código: **11/08/2026**

> Revisão de 11/08: a fatia vertical do chatbot foi implementada. As seções abaixo marcadas com 🔄 foram atualizadas; o restante ainda reflete o snapshot de 08/08.

---

## 1. TL;DR 🔄

- **~31% do MVP1 concluído** — 55 de 182 tarefas (eram 40).
- **O chat funciona ponta a ponta.** Paciente pergunta em `/chat/`, o bot consulta Oracle 23ai (incluindo AI Vector Search) e responde em streaming. 12 tarefas da Sprint 5 e 3 da Sprint 1 fechadas. Guia completo em [`CHAT_MVP.md`](CHAT_MVP.md).
- **Sprint 1 (fundação) em 65%** — 17/26. O banco **está modelado** para o subset do chat: 6 models, 6 migrations, aplicadas no Oracle real com rollback testado.
- **Sprint 0** segue 26/27 (falta só apresentar, S0-27).
- **`make setup`, `make test`, `make worker` e `make app` funcionam.** Os débitos #1, #2 e #3 estão resolvidos.
- **Sete bugs pré-existentes** foram encontrados e corrigidos no caminho — nenhum tinha a ver com o chat, e três deles (formato da `DATABASE_URL`, service name tratado como SID, `oracledb` sem teto de versão) impediam qualquer conexão com o Oracle. Lista em [`CHAT_MVP.md` §6](CHAT_MVP.md).
- **Ainda falta da S1-8:** Paciente, Consulta, Lead, Prontuario, Evolucao, LogAcesso e AgendaRegra. E o chat **não agenda** — as ferramentas são só de leitura.

---

## 2. Placar de sprints 🔄

Contagem por ID de tarefa (`SX-Y`), direto dos checkboxes de `sprints/*.md`.

| Sprint | Tarefas | Feitas | Abertas | % |
|---|---:|---:|---:|---:|
| S0 — Validação técnica | 27 | 26 | 1 | 🟢 96% |
| S1 — Fundação | 26 | 17 | 9 | 🟡 65% |
| S2 — CRM interno | 20 | 0 | 20 | ⚪ 0% |
| S3 — Agenda | 17 | 0 | 17 | ⚪ 0% |
| S4 — Site público | 23 | 0 | 23 | ⚪ 0% |
| S5 — Chatbot | 33 | 12 | 21 | 🟡 36% |
| S6 — Prontuário + hardening | 36 | 0 | 36 | ⚪ 0% |
| **Total** | **182** | **55** | **127** | **30%** |

**S1-8 conta como aberta**: entregou o subset do chat (Usuario, Especialidade,
Medico, MedicoEspecialidade, AgendaSlot, FaqVector, InteracaoChat), mas faltam
Paciente, Consulta, Lead, Prontuario, Evolucao, LogAcesso e AgendaRegra. Mesma
lógica em S1-16, cujo seeder ainda não cria pacientes.

**Definition of Done: 0 de 52 itens marcados** — em nenhuma sprint, nem na S0 que está 96%. Ou seja: nenhuma sprint foi formalmente encerrada, só suas tarefas.

---

## 3. O que existe de fato

**Andaime do projeto (S1-1 a S1-7)**

- Django 5.1 / Python 3.12, layout `apps/` + `config/`, 6 apps de domínio criados.
- Settings split em `base` / `dev` / `prod` / `test`, com `django-environ` + `.env.example`.
- `docker-compose.yml`: Oracle 23ai Free (`gvenzl/oracle-free:23-slim`, healthcheck), Redis 7, Mailhog, `django`, `celery-worker`. Dockerfile com Node 20 (para o Tailwind), usuário não-root, `tini`.
- `infra/scripts/setup.sh` (`make setup`) e `bootstrap.sh` — o restart do Oracle é necessário porque `vector_memory_size` é `SCOPE=SPFILE`.

**Segurança de PII (S1-13 a S1-15) — único código de domínio real**

`apps/core/security/`, 222 linhas em 4 arquivos:

- `crypto.py` — `CPFCipher` AES-256-GCM, nonce de 12 bytes via CSPRNG, token `base64url(nonce||ct||tag)`, AAD opcional.
- `hash.py` — `cpf_hash()` HMAC-SHA256 com pepper e `verify_cpf_hash()` com `hmac.compare_digest` (busca por CPF sem descriptografar).
- `keys.py` — geração de chave para `.env`.

**Frontend (S1-17)** — django-tailwind + app `apps/theme` com `base.html`, `components/_layout.html` e `static_src/`.

**Qualidade (S1-24 a S1-26)** — GitHub Actions com 3 jobs paralelos (lint, test+coverage, bandit), pre-commit com ruff/black, badge no README.

**Documentação** — 9 documentos em `docs/` + 5 ADRs. É a parte mais madura do repo.

---

## 4. O que ainda não existe 🔄

| Área | Estado |
|---|---|
| **Modelos de dados** | Parcial: 7 models e 6 migrations, aplicadas no Oracle. Faltam Paciente, Consulta, Lead, Prontuario, Evolucao, LogAcesso, AgendaRegra. |
| **Rotas** | `/admin/` e `/chat/` existem. O site público (S4) não. |
| **Views / telas** | Só o chat. CRM usa o Django Admin (ADR-0005); não há tela custom de agenda nem prontuário. |
| **Banco físico** | Índice HNSW em `FAQ_VECTOR` ✅ e UNIQUE de slot ✅. Falta o trigger PL/SQL de imutabilidade em `EVOLUCAO` (S1-10), que depende do model `Evolucao`. |
| **Celery** | Plugado, mas **sem nenhuma task**. O chat é síncrono. |
| **Agendamento pelo chat** | As ferramentas são só de leitura. Criar Lead e Consulta é a S5-12, fora do escopo desta entrega. |
| **Testes de aplicação** | 292 testes em CI + 16 contra Oracle + 5 contra o Ollama. Cobrem cripto, models, tools, SSE, guardrails e o loop de tool use. Não há teste E2E de browser. |

---

## 5. Débitos e travas conhecidas

Todos verificados nesta revisão, com evidência no código.

🔄 Os débitos #1, #2, #3, #6 e #7 foram **resolvidos** em 11/08 (marcados ✅ abaixo).

| # | Item | Evidência | Impacto |
|---|---|---|---|
| 1 | ✅ **Resolvido.** `AUTH_USER_MODEL` apontava para model inexistente | `apps/core/models.py` agora tem `Usuario(AbstractUser)` | Era pior do que registrado aqui: quebrava também o `pytest`, porque o `django.contrib.admin` resolve o user model no `ready()` |
| 2 | ✅ **Resolvido.** Celery não plugado | `config/celery.py` + `config/__init__.py` | — |
| 3 | ✅ **Resolvido.** Sem rota `/admin/` | `config/urls.py` com `/admin/` e `/chat/` | — |
| 4 | CI não exige cobertura mínima | [`.github/workflows/ci.yml:101`](../.github/workflows/ci.yml) roda `--cov` sem `--cov-fail-under` | O "70% mínimo nos módulos de domínio" do `CLAUDE.md` é só texto; a cobertura é informativa |
| 5 | bandit roda com `\|\| true` | [`.github/workflows/ci.yml:137`](../.github/workflows/ci.yml) | Achado de segurança não bloqueia merge. Já há um TODO no header do YAML para remover quando estabilizar |
| 6 | ✅ **Resolvido (parcial).** Dependências sem teto de versão | `ruff`, `black` e `oracledb` agora têm teto | O `oracledb` sem teto instalava a 4.x, incompatível com o Django 5.1 — **qualquer query estourava `TypeError`**. ruff/black sem teto faziam o CI reprovar sozinho conforme evoluíam |
| 7 | ✅ **Resolvido.** Marker `oracle` não registrado | `pyproject.toml` com seção `markers` + `conftest.py` na raiz com auto-skip | Com `--strict-markers`, usar o marker era **erro de coleta**: zero testes rodavam |
| 8 | **Aberto.** LLM local (Ollama `qwen2.5:3b`), não Anthropic | ADR-0006 pendente; interface `LLMClient` isola o provedor | O compromisso com a Anthropic segue de pé. Trocar é escrever outra implementação do Protocol, não mexer no `ChatService` |
| 9 | `.claude/worktrees/` untracked + 13 branches `worktree-agent-*` locais | `.gitignore:110` ignora só `.claude/settings.local.json` | Ruído no `git status` e na lista de branches |
| 10 | `main` local está 1 commit atrás do remoto | Remoto em `587c14d` (PR #6 mergeado); local em `63f1fa4` | Resolver com `git pull`. O conteúdo é idêntico ao de `feature/s1-block-c` |

---

## 6. Caminho crítico da S1

Restam **12 tarefas / ~47h estimadas**. A cadeia técnica é uma só, e começa em S1-8:

```
S1-8  Modelar 11 entidades em Django models        (BACK+DB, 8h)  ← raiz
  └── S1-9  Migrations Oracle com índices          (DB, 5h)
        ├── S1-10  Trigger PL/SQL de imutabilidade em EVOLUCAO  (DB, 3h)
        ├── S1-11  Constraint UNIQUE de slot                    (DB, 2h)
        └── S1-12  Índice HNSW em FAQ_VECTOR.EMBEDDING          (DB, 1h)
              └── S1-16  Seeders de clínica oftalmológica       (DB, 4h)
```

**S1-8 é o gargalo real: destrava 5 tarefas e resolve sozinha os débitos #1 e #3.** As 11 entidades são Especialidade · Medico/MedicoEspecialidade · Paciente · AgendaRegra/AgendaSlot · Consulta · Prontuario/Evolucao · Lead/InteracaoChat · FaqVector · Usuario · LogAcesso.

Trilhas **independentes** que podem correr em paralelo, sem esperar o banco:

- **Design** — S1-18 (paleta/tipografia/tokens, 6h) → S1-19 (logo, 2h), S1-20 (wireframes Figma, 10h)
- **Cliente** — S1-21 (kickoff, 2h) → S1-22 (assinatura da lista de fora-do-escopo, 1h)
- **Processo** — S1-23 (criar issues no GitHub para as sprints 1-6, 3h), S0-27 (apresentar a spike, 1h)

Dependências que atravessam sprints, para quem for planejar: S1-11 reaparece na S3-6 · S1-12 alimenta S5-13/S5-15 · S3-14 (`consultar_slots`) é consumida pela tool `buscar_slots` da S5-10 · S1-10 é validada no DoD da S6.

---

## 7. Rastreamento desatualizado

Se você olhar os arquivos e achar que nada foi feito, é isso:

- Os **7 arquivos de sprint** ainda têm `**Status:** ☐ Pendente` na linha 5 — inclusive a S0 (96%) e a S1 (54%).
- A tabela **Cronograma** do [`README.md`](../README.md) e a de status global de [`sprints/README.md`](../sprints/README.md) listam as 7 sprints como pendentes.
- **0/52 itens de Definition of Done** marcados.
- **Não há issues no GitHub** (a S1-23, que criaria o espelho, está aberta). Os `.md` de `sprints/` são a única fonte de verdade.

**A fazer:** atualizar cabeçalhos e tabelas, e priorizar a S1-23 — enquanto ela não sair, este documento e os `.md` são o único rastreamento que existe.

---

## 8. Cronograma vs. realidade

O plano original ([`PLANO.md`](PLANO.md)) é de **13 semanas**: Sprint 0 (1 sem) + Sprints 1-6 (2 sem cada).

| | |
|---|---|
| Primeiro commit | 23/05/2026 |
| Última atividade de código | **24/05/2026** |
| Data deste snapshot | 08/08/2026 |
| Commits no repo | 27, concentrados em 2 dias |
| PRs | 6, todos mergeados |

Na linha do tempo original, agosto cairia na **Sprint 5 (semanas 10-11)**. O projeto está na **Sprint 1**. O cronograma precisa ser rebaselinado a partir da data de retomada — o dado está aqui para isso, não como cobrança.

---

## 9. Como rodar hoje

Detalhes e troubleshooting em [`SETUP.md`](SETUP.md). Não é preciso ter Python no host — só Docker + Compose v2.

🔄 **Pré-requisitos do chat** (uma vez):

```bash
ollama pull qwen2.5:3b && ollama pull paraphrase-multilingual
```

**Funciona:**

```bash
bash infra/scripts/bootstrap.sh   # stack + restart que ativa vector_memory_size
make migrate                      # aplica no Oracle 23ai
make seed                         # especialidades, médicos, slots e FAQs
make test                         # 292 testes, SQLite em memória
make test-oracle                  # 16 testes contra Oracle real (VECTOR/HNSW)
make test-llm                     # 5 testes contra o Ollama
make lint / make fmt
make app                          # http://localhost:8000/chat/ e /admin/
```

Depois do `make seed`, rode `docker compose run --rm django python manage.py reindexar_faq`
para gerar os embeddings — sem isso a busca semântica não devolve nada.

**Atenção a portas:** os defaults de Redis e Mailhog saem deslocados (6380, 1026/8026)
para conviver com outras stacks na mesma máquina. Ajuste no `.env` se precisar.

---

## 10. Riscos ativos relevantes

Registro completo em [`RISCOS.md`](RISCOS.md) — 12 riscos, **todos ainda com status 🟢 Ativo**, nenhum resolvido nem materializado. Os que pesam agora:

| ID | Risco | Impacto | Por que importa hoje |
|---|---|---|---|
| R1 | LGPD inadequada na entrega final | 🔴 Crítico | A mitigação começou bem (cripto de CPF pronta e testada), mas `LogAcesso` só nasce na S1-8 |
| R8 | Scope creep | 🟠 Alto | [`ESCOPO.md`](ESCOPO.md) segue **sem assinatura do cliente** — a S1-22 é justamente essa mitigação, e está aberta |
| R11 | Cliente piloto desistir no meio | 🟡 Médio | O kickoff (S1-21) ainda não aconteceu, e a S1 é a sprint das semanas 2-3 |
| R7 | Custo da API do Claude estourar | 🟡 Médio | Ligado ao débito #8: o custo real nunca foi medido, porque a validação usou modelo local |

---

*Snapshot gerado a partir do estado do repositório em 08/08/2026. Números conferidos contra os checkboxes de `sprints/*.md` e o código em `apps/`, `config/` e `infra/`.*

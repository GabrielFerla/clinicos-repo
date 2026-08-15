# Status do Projeto — ClinicOS MVP1

> Documento vivo, escrito para o time técnico. Snapshot do que **existe de fato no código** — não do que está planejado. Regenerar ao fim de cada sprint. Para o plano, ver [`PLANO.md`](PLANO.md); para o escopo, [`ESCOPO.md`](ESCOPO.md); para as tarefas, [`sprints/`](../sprints/).

**Snapshot:** 14/08/2026 · branch `feature/s1-8-modelagem-completa` · última atividade de código: **14/08/2026**

> Revisão de 14/08: a S1-8 foi fechada — as 14 entidades da [`ARQUITETURA.md`](ARQUITETURA.md) existem no Oracle, com o trigger de imutabilidade (S1-10) e os seeders (S1-16). As seções marcadas com 🔄 foram atualizadas nesta rodada.

---

## 1. TL;DR 🔄

- **~32% do MVP1 concluído** — 58 de 182 tarefas (eram 55).
- **A trilha técnica da Sprint 1 está encerrada.** Restam só design (S1-18 a S1-20), cliente (S1-21, S1-22) e processo (S1-23) — nada disso é código.
- **O schema está completo.** 14 models, 12 migrations, aplicadas no Oracle 23ai real com rollback testado. `EVOLUCAO` é append-only por trigger PL/SQL, não por convenção.
- **O chat funciona ponta a ponta.** Paciente pergunta em `/chat/`, o bot consulta Oracle 23ai (incluindo AI Vector Search) e responde em streaming. Guia completo em [`CHAT_MVP.md`](CHAT_MVP.md).
- **Sprint 1 em 77%** — 20/26. **Sprint 0** segue 26/27 (falta só apresentar, S0-27). **Sprint 5** em 12/33.
- **`make setup`, `make test`, `make seed`, `make worker` e `make app` funcionam.** Os débitos #1, #2, #3, #6, #7 e #11 estão resolvidos.
- **O que a S1-8 destrava:** Sprint 2 inteira (CRUD de Paciente, permissões, audit log), Sprint 3 (`gerar_slots`, `AgendamentoService`) e o agendamento pelo chat (S5-12, S5-22, S5-24).
- **O chat ainda não agenda** — as ferramentas seguem sendo só de leitura. Agora é falta de tool, não de tabela.

---

## 2. Placar de sprints 🔄

Contagem por ID de tarefa (`SX-Y`), direto dos checkboxes de `sprints/*.md`.

| Sprint | Tarefas | Feitas | Abertas | % |
|---|---:|---:|---:|---:|
| S0 — Validação técnica | 27 | 26 | 1 | 🟢 96% |
| S1 — Fundação | 26 | 20 | 6 | 🟢 77% |
| S2 — CRM interno | 20 | 0 | 20 | ⚪ 0% |
| S3 — Agenda | 17 | 0 | 17 | ⚪ 0% |
| S4 — Site público | 23 | 0 | 23 | ⚪ 0% |
| S5 — Chatbot | 33 | 12 | 21 | 🟡 36% |
| S6 — Prontuário + hardening | 36 | 0 | 36 | ⚪ 0% |
| **Total** | **182** | **58** | **124** | **32%** |

**S1-8, S1-10 e S1-16 fecharam em 14/08.** As 6 tarefas abertas da S1 não são de
código: S1-18/19/20 (design), S1-21/22 (cliente) e S1-23 (issues no GitHub).

**Definition of Done: 3 de 52 itens marcados**, todos na S1 — migrate no Oracle
sem erros, trigger de imutabilidade testado e helpers de CPF cobertos. Os demais
seguem abertos, inclusive na S0 que está 96%.

---

## 3. O que existe de fato 🔄

**Schema completo (S1-8 a S1-12, S1-16)**

14 models em 4 apps de domínio, 12 migrations, todas aplicadas no Oracle 23ai
com rollback testado:

| App | Models |
|---|---|
| `core` | `Usuario` (AbstractUser, perfis ADMIN/MEDICO/RECEPCAO) |
| `crm` | `Especialidade`, `Medico`, `MedicoEspecialidade`, `Paciente`, `Lead` |
| `agenda` | `AgendaRegra`, `AgendaSlot`, `Consulta` |
| `prontuario` | `Prontuario`, `Evolucao`, `LogAcesso` |
| `chatbot` | `FaqVector`, `InteracaoChat` |

As três garantias que moram no banco, e não na aplicação:

- **`TRG_EVOLUCAO_IMUTAVEL`** — `BEFORE UPDATE OR DELETE` em `EVOLUCAO`, levanta
  `ORA-20001`. Exigência CFM de prontuário não-alterável; no banco, nem bug da
  aplicação nem SQL fora do ORM corrompem o registro. Coberto por teste Oracle.
- **`UK_SLOT_MEDICO_HORARIO`** + `Consulta.slot` OneToOne — anti-overbooking em
  duas camadas.
- **CPF nunca em claro** — `Paciente.definir_cpf()` cifra (AES-256-GCM) e
  hasheia (HMAC-SHA256 com pepper) numa operação só; `buscar_por_cpf()` acha sem
  descriptografar nada.

**Andaime do projeto (S1-1 a S1-7)**

- Django 5.1 / Python 3.12, layout `apps/` + `config/`, 6 apps de domínio criados.
- Settings split em `base` / `dev` / `prod` / `test`, com `django-environ` + `.env.example`.
- `docker-compose.yml`: Oracle 23ai Free (`gvenzl/oracle-free:23-slim`, healthcheck), Redis 7, Mailhog, `django`, `celery-worker`. Dockerfile com Node 20 (para o Tailwind), usuário não-root, `tini`.
- `infra/scripts/setup.sh` (`make setup`) e `bootstrap.sh` — o restart do Oracle é necessário porque `vector_memory_size` é `SCOPE=SPFILE`.

**Segurança de PII (S1-13 a S1-15)**

`apps/core/security/`, 222 linhas em 4 arquivos — consumido pelo `Paciente`
desde 14/08:

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
| **Modelos de dados** | ✅ **Completo.** 14 models e 12 migrations, aplicadas no Oracle com rollback testado. As 14 entidades da [`ARQUITETURA.md`](ARQUITETURA.md) existem. |
| **Banco físico** | ✅ Índice HNSW em `FAQ_VECTOR`, UNIQUE de slot e trigger `TRG_EVOLUCAO_IMUTAVEL` (ENABLED/VALID, verificado em `USER_TRIGGERS`). |
| **Dados de demonstração** | ✅ 50 pacientes (CPF cifrado), 5 médicos, 28 regras, 600+ slots, 13 consultas, 13 leads, 4 prontuários, 20 FAQs. `make seed` é idempotente. |
| **Rotas** | `/admin/` e `/chat/` existem. O site público (S4) não. |
| **Views / telas** | Só o chat. CRM usa o Django Admin (ADR-0005); não há tela custom de agenda nem prontuário. **Os models novos não estão registrados no Admin** — é a S2-7 a S2-9. |
| **Services** | Nenhum. `AgendamentoService` é a S3-7; a geração de slots a partir das regras é a S3-3. Os models estão prontos para ambos. |
| **Celery** | Plugado, mas **sem nenhuma task**. O chat é síncrono. |
| **Agendamento pelo chat** | As ferramentas seguem só de leitura. Agora é falta de tool (S5-12), não de tabela. |
| **Auditoria LGPD** | Tabela `LOG_ACESSO` existe e está vazia de propósito. O middleware que a popula é da Sprint 6. |
| **Testes de aplicação** | 412 em CI + 21 contra Oracle + 5 contra o Ollama. Cobrem cripto, models, constraints, trigger de imutabilidade, seeder, tools, SSE, guardrails e o loop de tool use. Não há teste E2E de browser. |

---

## 5. Débitos e travas conhecidas 🔄

Todos verificados nesta revisão, com evidência no código.

🔄 Os débitos #1, #2, #3, #6 e #7 foram resolvidos em 11/08; o #10 e o #11 em 14/08.

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
| 10 | ✅ **Resolvido.** `main` local atrás do remoto | `git rev-list --left-right --count origin/main...main` → `0 0` | — |
| 11 | ✅ **Resolvido.** `CPF_ENCRYPTION_KEY` do CI não era base64url válido | Removida de [`.github/workflows/ci.yml`](../.github/workflows/ci.yml); o `conftest.py:36` já provê chave válida | Latente desde a S1-13: nada consumia a chave no import, então ninguém notou. Ao surgir o model `Paciente`, a coleta do pytest quebrava (3 failed, 13 errors). Como o `conftest.py` usa `setdefault`, o valor ruim do workflow **vencia** o bom |
| 12 | **Aberto.** Models novos sem registro no Admin | `apps/crm/admin.py`, `apps/agenda/admin.py`, `apps/prontuario/admin.py` seguem vazios para as entidades novas | Os dados semeados existem mas não são visíveis pela UI. É exatamente o escopo da S2-7 a S2-9, então não é surpresa — só não confundir "tabela existe" com "dá para usar" |

---

## 6. Caminho crítico 🔄

**A cadeia técnica da S1 acabou.** S1-8 → S1-9 → S1-10/11/12 → S1-16 está toda
fechada. As 6 tarefas restantes da S1 não são de código e correm em paralelo,
sem depender umas das outras:

- **Design** — S1-18 (paleta/tipografia/tokens, 6h) → S1-19 (logo, 2h), S1-20 (wireframes Figma, 10h)
- **Cliente** — S1-21 (kickoff, 2h) → S1-22 (assinatura da lista de fora-do-escopo, 1h)
- **Processo** — S1-23 (criar issues no GitHub para as sprints 1-6, 3h), S0-27 (apresentar a spike, 1h)

O gargalo mudou de lugar. Com o schema pronto, três frentes de código abrem ao
mesmo tempo, e a escolha entre elas é de prioridade, não de dependência:

```
schema completo (S1-8/9/10/11/12/16)  ✅
  ├── Sprint 2 — Admin sobre os models novos    (S2-7 a S2-9)  ← torna os dados usáveis
  ├── Sprint 3 — gerar_slots (S3-3) → AgendamentoService (S3-7) → consultar_slots (S3-14)
  └── Sprint 5 — criar_lead_e_consulta (S5-12) → funil (S5-22/23/24)
```

**A S3-7 é a nova raiz do agendamento:** a S5-12 (agendar pelo chat) precisa
dela, porque criar `Consulta` fora de transação serializável fura o
anti-overbooking que o schema agora garante.

Dependências que atravessam sprints, para quem for planejar: S1-11 reaparece na
S3-6 · S1-12 alimenta S5-13/S5-15 · S3-14 (`consultar_slots`) é consumida pela
tool `buscar_slots` da S5-10 · S1-10 é validada no DoD da S6.

---

## 7. Rastreamento 🔄

Melhorou parcialmente em 14/08:

- ✅ O cabeçalho da **S1** e a tabela de status de [`sprints/README.md`](../sprints/README.md) refletem o progresso real das sprints 0, 1 e 5.
- ✅ **3/52 itens de Definition of Done** marcados (eram 0), todos na S1.
- ⚠️ Os arquivos das sprints **2, 3, 4 e 6** ainda têm `**Status:** ☐ Pendente` na linha 5 — mas essas estão de fato em 0%, então o rótulo está correto.
- ⚠️ A tabela **Cronograma** do [`README.md`](../README.md) segue listando as 7 sprints como pendentes.
- ❌ **Não há issues no GitHub** (a S1-23, que criaria o espelho, está aberta). Os `.md` de `sprints/` seguem sendo a única fonte de verdade.

**A fazer:** priorizar a S1-23 — enquanto ela não sair, este documento e os `.md` são o único rastreamento que existe.

---

## 8. Cronograma vs. realidade

O plano original ([`PLANO.md`](PLANO.md)) é de **13 semanas**: Sprint 0 (1 sem) + Sprints 1-6 (2 sem cada).

| | |
|---|---|
| Primeiro commit | 23/05/2026 |
| Última atividade de código | **14/08/2026** |
| Data deste snapshot | 14/08/2026 |
| Commits no repo | 48, concentrados em 4 dias |
| PRs | 7, todos mergeados |

Na linha do tempo original, agosto cairia na **Sprint 5 (semanas 10-11)**. O projeto está encerrando a **Sprint 1**. O cronograma precisa ser rebaselinado a partir da data de retomada — o dado está aqui para isso, não como cobrança.

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
make seed                         # 50 pacientes, médicos, regras, slots, consultas, leads e FAQs (idempotente)
make test                         # 412 testes, SQLite em memória
make test-oracle                  # 21 testes contra Oracle real (VECTOR/HNSW + trigger)
make test-llm                     # 5 testes contra o Ollama
make lint / make fmt
make app                          # http://localhost:8000/chat/ e /admin/
```

Depois do `make seed`, rode `docker compose run --rm django python manage.py reindexar_faq`
para gerar os embeddings — sem isso a busca semântica não devolve nada.

**Atenção a portas:** os defaults de Redis e Mailhog saem deslocados (6380, 1026/8026)
para conviver com outras stacks na mesma máquina. Ajuste no `.env` se precisar.

---

## 10. Riscos ativos relevantes 🔄

Registro completo em [`RISCOS.md`](RISCOS.md) — 12 riscos, **todos ainda com status 🟢 Ativo**, nenhum resolvido nem materializado. Os que pesam agora:

| ID | Risco | Impacto | Por que importa hoje |
|---|---|---|---|
| R1 | LGPD inadequada na entrega final | 🔴 Crítico | Avançou em 14/08: `Paciente` grava CPF cifrado (AES-256-GCM) com busca por HMAC, e `LOG_ACESSO` existe. Mas a tabela está **vazia** — sem o middleware da Sprint 6 não há auditoria de fato, só o lugar para guardá-la |
| R8 | Scope creep | 🟠 Alto | [`ESCOPO.md`](ESCOPO.md) segue **sem assinatura do cliente** — a S1-22 é justamente essa mitigação, e está aberta |
| R11 | Cliente piloto desistir no meio | 🟡 Médio | O kickoff (S1-21) ainda não aconteceu, e a S1 é a sprint das semanas 2-3 |
| R7 | Custo da API do Claude estourar | 🟡 Médio | Ligado ao débito #8: o custo real nunca foi medido, porque a validação usou modelo local |

---

*Snapshot gerado a partir do estado do repositório em 14/08/2026. Números conferidos contra os checkboxes de `sprints/*.md`, o código em `apps/`, `config/` e `infra/`, e o Oracle 23ai real (`USER_TABLES`, `USER_TRIGGERS` e contagens após `make seed`).*

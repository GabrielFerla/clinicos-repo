# Status do Projeto — ClinicOS MVP1

> Documento vivo, escrito para o time técnico. Snapshot do que **existe de fato no código** — não do que está planejado. Regenerar ao fim de cada sprint. Para o plano, ver [`PLANO.md`](PLANO.md); para o escopo, [`ESCOPO.md`](ESCOPO.md); para as tarefas, [`sprints/`](../sprints/).

**Snapshot:** 08/08/2026 · `main` @ `587c14d` · última atividade de código: **24/05/2026**

---

## 1. TL;DR

- **22% do MVP1 concluído** — 40 de 182 tarefas.
- **Sprint 0 (validação técnica) fechada** em 26/27: a stack foi provada ponta a ponta num repo separado (`clinicos-spike`). Falta só apresentar os resultados (S0-27).
- **Sprint 1 (fundação) em 54%** — 14/26. O que foi entregue é *andaime*: repo, Docker, settings, CI, Tailwind.
- **O único código de domínio que existe são 222 linhas de criptografia de CPF** (`apps/core/security/`), com 87 testes. Todo o resto dos apps é esqueleto.
- **O banco ainda não foi modelado.** Zero models, zero migrations. Isso é a S1-8, e ela trava 5 outras tarefas.
- **`make setup` não completa hoje** e `make worker` quebra — ver [§5](#5-débitos-e-travas-conhecidas). São gaps esperados, mas até agora não documentados.

---

## 2. Placar de sprints

Contagem por ID de tarefa (`SX-Y`), direto dos checkboxes de `sprints/*.md`.

| Sprint | Tarefas | Feitas | Abertas | % |
|---|---:|---:|---:|---:|
| S0 — Validação técnica | 27 | 26 | 1 | 🟢 96% |
| S1 — Fundação | 26 | 14 | 12 | 🟡 54% |
| S2 — CRM interno | 20 | 0 | 20 | ⚪ 0% |
| S3 — Agenda | 17 | 0 | 17 | ⚪ 0% |
| S4 — Site público | 23 | 0 | 23 | ⚪ 0% |
| S5 — Chatbot | 33 | 0 | 33 | ⚪ 0% |
| S6 — Prontuário + hardening | 36 | 0 | 36 | ⚪ 0% |
| **Total** | **182** | **40** | **142** | **22%** |

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

## 4. O que ainda não existe

| Área | Estado |
|---|---|
| **Modelos de dados** | Os 6 `models.py` têm 3 linhas cada (só o `import`). **Zero migrations** — todas as pastas `migrations/` contêm apenas `__init__.py`. |
| **Rotas** | `config/urls.py` tem `urlpatterns = []`. Nenhuma URL registrada, nem `/admin/`. |
| **Views / telas** | Nenhuma. Os `views.py` dos apps estão vazios. |
| **Banco físico** | Sem seeders, sem trigger PL/SQL de imutabilidade em `EVOLUCAO`, sem constraint UNIQUE de slot, sem índice HNSW em `FAQ_VECTOR`. |
| **Celery** | Não plugado — ver débito #2. |
| **Testes de aplicação** | Os 6 `tests.py` dos apps são stubs de 3 linhas, **0 testes**. Os 87 testes existentes cobrem só os helpers de cripto, que são funções puras sem ORM. |

---

## 5. Débitos e travas conhecidas

Todos verificados nesta revisão, com evidência no código.

| # | Item | Evidência | Impacto |
|---|---|---|---|
| 1 | `AUTH_USER_MODEL = "core.Usuario"` aponta para um model que não existe | [`config/settings/base.py:225`](../config/settings/base.py) (com `TODO(S1-8)` explícito nas linhas 221-224) | `makemigrations`/`migrate` falham → **`make setup` não completa**, apesar do README prometer setup em 1 comando |
| 2 | Celery não plugado: não existe `config/celery.py` e `config/__init__.py` está com **0 bytes** | `Makefile:9` e o serviço `celery-worker` do compose chamam `celery -A config worker` | `make worker` quebra e o container `celery-worker` não sobe |
| 3 | Sem rota `/admin/` | [`config/urls.py:9`](../config/urls.py) | `setup.sh` anuncia `http://localhost:8000/admin/` e cria o superuser `admin/admin` — que hoje é inalcançável |
| 4 | CI não exige cobertura mínima | [`.github/workflows/ci.yml:101`](../.github/workflows/ci.yml) roda `--cov` sem `--cov-fail-under` | O "70% mínimo nos módulos de domínio" do `CLAUDE.md` é só texto; a cobertura é informativa |
| 5 | bandit roda com `\|\| true` | [`.github/workflows/ci.yml:137`](../.github/workflows/ci.yml) | Achado de segurança não bloqueia merge. Já há um TODO no header do YAML para remover quando estabilizar |
| 6 | Pin do Django divergente | `pyproject.toml:12` diz `<6.0`; `infra/django/requirements/base.txt:5` diz `<5.2` | Risco de drift entre o que o CI instala e o que o Docker instala. A fonte de verdade prática é `requirements/` |
| 7 | Marker `@pytest.mark.oracle` é citado mas não registrado | `pyproject.toml:75` tem `--strict-markers` e **nenhuma seção `markers`**; `ci.yml:12` já se refere ao marker | Usar o marker hoje **quebra a suíte**. Registrar antes da S1-9 |
| 8 | Spike do Claude foi validado contra Ollama `qwen3:8b`, não contra a Anthropic API | `clinicos-spike/checkpoint-4` (repo separado) | Tool Use e streaming precisam ser **revalidados com a API real antes da S5** |
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

**Funciona:**

```bash
make up      # Oracle 23ai + Redis + Mailhog
make test    # pytest — 87 testes de cripto, SQLite em memória
make lint    # ruff + black --check
make fmt     # ruff --fix + black
```

**Ainda não funciona** (esperado até a S1-8/S1-9):

| Comando | Por quê |
|---|---|
| `make setup` | Sobe os serviços, mas falha no `migrate` — débito #1 |
| `make worker` | Não há app Celery em `config` — débito #2 |
| `make app` | Sobe o runserver, mas `urlpatterns` está vazio: nenhuma rota, nem `/admin/` — débito #3 |

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

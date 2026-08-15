# Status do Projeto — ClinicOS MVP1

> Documento vivo, escrito para o time técnico. Snapshot do que **existe de fato no código** — não do que está planejado. Regenerar ao fim de cada sprint. Para o plano, ver [`PLANO.md`](PLANO.md); para o escopo, [`ESCOPO.md`](ESCOPO.md); para as tarefas, [`sprints/`](../sprints/).

**Snapshot:** 14/08/2026 · branch `feature/mini-crm-chat-agendamento` · última atividade de código: **14/08/2026**

> Revisão de 14/08 (segunda rodada do dia): entregue a fatia vertical **"mini CRM + chat que agenda"**, cortando as sprints 2, 3 e 5. O Admin passou a expor as 14 entidades e o chatbot deixou de ser só de leitura. As seções marcadas com 🔄 foram atualizadas nesta rodada.

---

## 1. TL;DR 🔄

- **~40% do MVP1 concluído** — 72 de 182 tarefas (eram 58).
- **O chat agenda de verdade.** A tool `criar_lead_e_consulta` cria ou reaproveita o paciente pelo CPF, grava a `Consulta` via `AgendamentoService` e move o lead da conversa para `AGENDADO`. Verificado contra o Oracle real: 19/19 checagens ponta a ponta.
- **O CRM é utilizável.** As 14 entidades têm tela no Admin, com filtro, busca e paginação. O débito #12 está resolvido.
- **O anti-overbooking está provado, não só declarado.** `AgendamentoService.agendar` roda em `atomic()` + `select_for_update()`, e as duas constraints foram conferidas no `USER_CONSTRAINTS` do Oracle. O `ConsultaAdmin` também passa pelo service — senão a recepção deixaria o slot `LIVRE` e o chatbot seguiria oferecendo o horário.
- **A agenda se abastece sozinha.** `gerar_slots --dias 60` expande as 28 regras semeadas em 2364 slots e é idempotente (segunda execução: 0 criados).
- **A trilha técnica da Sprint 1 segue encerrada.** Restam design (S1-18 a S1-20), cliente (S1-21, S1-22) e processo (S1-23) — nada disso é código.
- **Sprint 0** 26/27 · **Sprint 1** 20/26 · **Sprint 2** 6/20 · **Sprint 3** 4/17 · **Sprint 5** 16/33.
- **`make setup`, `make test`, `make seed`, `make worker` e `make app` funcionam.** Os débitos #1, #2, #3, #6, #7, #11 e #12 estão resolvidos.
- **O que falta para o chat estar completo:** a conversa inteira conduzida pelo `qwen2.5:3b` ainda não foi validada à mão — a tool está provada, o diálogo que a aciona não.

---

## 2. Placar de sprints 🔄

Contagem por ID de tarefa (`SX-Y`), direto dos checkboxes de `sprints/*.md`.

| Sprint | Tarefas | Feitas | Abertas | % |
|---|---:|---:|---:|---:|
| S0 — Validação técnica | 27 | 26 | 1 | 🟢 96% |
| S1 — Fundação | 26 | 20 | 6 | 🟢 77% |
| S2 — CRM interno | 20 | 6 | 14 | 🟡 30% |
| S3 — Agenda | 17 | 4 | 13 | 🟡 24% |
| S4 — Site público | 23 | 0 | 23 | ⚪ 0% |
| S5 — Chatbot | 33 | 16 | 17 | 🟡 48% |
| S6 — Prontuário + hardening | 36 | 0 | 36 | ⚪ 0% |
| **Total** | **182** | **72** | **110** | **40%** |

**14 tarefas fecharam na fatia de 14/08**, atravessando três sprints: S2-3, S2-10,
S2-13, S2-16, S2-17, S2-18 · S3-3, S3-6, S3-7, S3-8 · S5-12, S5-23, S5-24, S5-27.

Duas ficaram **deliberadamente abertas por serem parciais**, para não inflar o placar:
**S2-9** (o CRUD de paciente funciona; faltam só os campos oftalmológicos, que exigem
migration) e **S3-10** (o Admin da agenda existe; faltam os "componentes visuais").
O detalhe está nas Notas de cada sprint.

**Definition of Done: 9 de 52 itens marcados** (eram 3). Os 6 novos: CPF cifrado
verificado no banco, busca por hash, médico restrito aos seus pacientes e bloqueio de
acesso alheio (S2); corrida no mesmo slot com um só vencedor (S3); funil com leads em
etapas distintas (S5).

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

**CRM operável no Admin (S2-9 parcial, S2-10, S2-13, S5-23, S5-27, S3-10 parcial)**

As 14 entidades têm tela, com filtro, busca e paginação. O que não é CRUD trivial:

- **`PacienteAdmin`** — o model não tem campo `cpf` em claro, então o form declara um
  campo não-model: valida os dois dígitos verificadores (`validar_cpf`), recusa
  duplicado consultando `cpf_hash` e grava por `definir_cpf()`. A listagem mostra
  `***.***.789-09`; digitar os 11 dígitos na busca acha o paciente **sem descriptografar
  nada**.
- **Somente leitura de verdade** em `Evolucao`, `LogAcesso` e `InteracaoChat`: as três
  permissões negadas mais `get_readonly_fields` cobrindo todo campo concreto. Em
  `Evolucao` não é preferência de UX — `TRG_EVOLUCAO_IMUTAVEL` levanta `ORA-20001`, e
  uma tela editável só produziria erro 500.
- **Médico enxerga só o que é dele** — `get_queryset` recortado por perfil em consulta,
  paciente e prontuário, apoiado no novo `Medico.usuario`. Médico sem vínculo vê lista
  vazia, e não tudo.

**Agendamento (S3-3, S3-6, S3-7, S3-8, S5-12, S5-24)**

- **`AgendamentoService.agendar`** — `atomic()` + `select_for_update()`, recusa slot
  ocupado ou no passado, deriva `medico` de `slot.medico` (é keyword-only e **não**
  aceita médico), marca o slot `RESERVADO`. `IntegrityError` de corrida e slot já tomado
  saem pela mesma `SlotIndisponivelError`, com mensagem exibível ao paciente.
- **`gerar_slots --dias 60`** — expande as regras semanais respeitando duração,
  intervalo e vigência. Idempotente.
- **`criar_lead_e_consulta`** — a primeira tool de escrita do chatbot. `slot_id` só vem
  de um `buscar_slots` anterior; o `conversa_id` é injetado pela view depois de
  conferido contra a sessão, nunca pelo modelo.

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
| **Views / telas** | ✅ **As 14 entidades têm tela no Admin** (ADR-0005), com filtro, busca e paginação. Não há tela custom de agenda (calendário é S3-11) nem de prontuário. |
| **Services** | ✅ `AgendamentoService` (S3-7) e o command `gerar_slots` (S3-3) existem. Falta o resto da S3: exceções, Celery Beat e as telas. |
| **Celery** | Plugado, mas **sem nenhuma task**. O chat é síncrono, e o `gerar_slots` roda à mão — o job diário é a S3-4. |
| **Agendamento pelo chat** | ✅ **Funciona.** `criar_lead_e_consulta` fecha o agendamento e move o lead para `AGENDADO`. Falta cancelar (S5-14) e triagem por sintoma (S5-11). |
| **Auditoria LGPD** | Tabela `LOG_ACESSO` existe, tem tela somente-leitura e segue **vazia**: o middleware que a popula é da Sprint 6. Ter onde guardar não é ter auditoria. |
| **Notificações** | Nenhuma. Quem agenda pelo chat **não recebe e-mail de confirmação** (S3-16/17, S5-29/30). O Mailhog está no ar sem ninguém mandar nada. |
| **Anti-abuso no chat** | Nenhum. Sem rate limit (S5-18), honeypot (S5-19) nem bloqueio por palavra-chave (S5-21) — e agora a superfície é maior, porque o chat **escreve** no banco. |
| **Testes de aplicação** | 591 em CI + 24 contra Oracle + 5 contra o Ollama. Cobrem cripto, models, constraints, trigger de imutabilidade, seeder, tools, SSE, guardrails, loop de tool use, os CRUDs do Admin, permissões por perfil, geração de slots e anti-overbooking. Não há teste E2E de browser. |

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
| 12 | ✅ **Resolvido.** Models novos sem registro no Admin | As 14 entidades registradas em `apps/{crm,agenda,prontuario,chatbot,core}/admin.py` | — |
| 13 | **Aberto.** `bulk_create(ignore_conflicts=True)` não existe no Oracle | O backend do Django declara `supports_ignore_conflicts = False`; a flag levanta `NotSupportedError` | Pegadinha que deixa a suíte **verde no SQLite com o código quebrado em produção**. O `gerar_slots` já condiciona a flag a `connection.features` e cai para savepoint linha a linha no Oracle. Fica registrado porque a S3-4 (Celery Beat) reusa esse caminho |
| 14 | **Aberto.** Chat escreve no banco sem nenhum anti-abuso | Não há rate limit (S5-18), honeypot (S5-19) nem bloqueio por palavra-chave (S5-21) | Mudou de peso em 14/08: enquanto as tools eram só de leitura, abuso custava CPU. Agora um script consegue **criar paciente e ocupar agenda em massa** por `/chat/` |
| 15 | **Aberto.** Quem agenda pelo chat não recebe confirmação | Nenhum e-mail implementado (S3-16/17, S5-29/30); Mailhog no ar sem remetente | O paciente fecha o agendamento e sai sem comprovante. É o buraco mais visível para o cliente piloto |

---

## 6. Caminho crítico 🔄

**A cadeia técnica da S1 acabou.** S1-8 → S1-9 → S1-10/11/12 → S1-16 está toda
fechada. As 6 tarefas restantes da S1 não são de código e correm em paralelo,
sem depender umas das outras:

- **Design** — S1-18 (paleta/tipografia/tokens, 6h) → S1-19 (logo, 2h), S1-20 (wireframes Figma, 10h)
- **Cliente** — S1-21 (kickoff, 2h) → S1-22 (assinatura da lista de fora-do-escopo, 1h)
- **Processo** — S1-23 (criar issues no GitHub para as sprints 1-6, 3h), S0-27 (apresentar a spike, 1h)

**A cadeia do agendamento também acabou.** `gerar_slots` (S3-3) → `AgendamentoService`
(S3-7) → `criar_lead_e_consulta` (S5-12) → funil (S5-24) está fechada e provada contra o
Oracle. Não há mais uma raiz técnica bloqueando outras frentes.

O gargalo agora é de **confiabilidade e de produto**, não de dependência:

```
fatia vertical operando (CRM + chat que agenda)  ✅
  ├── Confirmação por e-mail   (S3-16/17, S5-29/30)  ← débito #15; o paciente sai sem comprovante
  ├── Anti-abuso no chat       (S5-18/19/21)         ← débito #14; agora o chat escreve
  ├── Job diário de slots      (S3-4)                ← a agenda seca em 60 dias sem isso
  ├── Auditoria LGPD de fato   (middleware da S6)    ← risco R1; LOG_ACESSO segue vazio
  └── Sprint 4 — site público                        ← nada dela existe, e é onde o chat mora
```

**A ordem sugerida é essa mesma.** Os dois primeiros são os que separam "demo que
funciona" de "sistema que um paciente real usa": sem e-mail o agendamento não tem
comprovante, e sem rate limit um script ocupa a agenda inteira por `/chat/`.

Dependências que atravessam sprints, para quem for planejar: S1-12 alimenta
S5-13/S5-15 · a S3-4 reusa o `gerar_slots` e herda o débito #13 · S3-14
(`consultar_slots`) virou redundante na prática, já que a tool `buscar_slots` consulta o
ORM direto · S1-10 é validada no DoD da S6.

---

## 7. Rastreamento 🔄

Melhorou parcialmente em 14/08:

- ✅ Os cabeçalhos das sprints **1, 2, 3 e 5** e a tabela de [`sprints/README.md`](../sprints/README.md) refletem o progresso real.
- ✅ **9/52 itens de Definition of Done** marcados (eram 3).
- ✅ **Tarefa parcial não vira checkbox marcado.** S2-9 e S3-10 seguem `[ ]` com o que falta descrito nas Notas da sprint — o placar acima conta checkbox, então marcar parcial corromperia o número.
- ⚠️ Os arquivos das sprints **4 e 6** ainda têm `**Status:** ☐ Pendente` — corretíssimo, estão em 0%.
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
| Commits no repo | 57, concentrados em 4 dias |
| PRs | 7 mergeados + 1 aberto (`feature/mini-crm-chat-agendamento`) |

Na linha do tempo original, agosto cairia na **Sprint 5 (semanas 10-11)**. O projeto tem a Sprint 1 encerrada e fatias das sprints 2, 3 e 5 em pé. O cronograma precisa ser rebaselinado a partir da data de retomada — o dado está aqui para isso, não como cobrança.

**Nota de método:** a execução deixou de seguir sprint por sprint e passou a cortar fatias verticais (a de 14/08 pegou S2 + S3 + S5 de uma vez). Faz sentido para um MVP guiado por demo, mas significa que o "% da sprint" acima mede cobertura de tarefa, **não** prontidão para entrega — uma sprint em 30% pode ter o fluxo principal funcionando enquanto uma em 77% não tem.

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
docker compose run --rm django python manage.py gerar_slots --dias 60   # expande as regras (idempotente)
make test                         # 591 testes, SQLite em memória
make test-oracle                  # 24 testes contra Oracle real (VECTOR/HNSW + trigger + anti-overbooking)
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
| R1 | LGPD inadequada na entrega final | 🔴 Crítico | Avançou de novo em 14/08: o CPF entra cifrado pelo Admin, a busca é por HMAC e o médico só enxerga os próprios pacientes. Mas `LOG_ACESSO` continua **vazia** — sem o middleware da Sprint 6 não há auditoria de fato, só o lugar para guardá-la. E agora há mais acesso a registrar, não menos |
| R8 | Scope creep | 🟠 Alto | [`ESCOPO.md`](ESCOPO.md) segue **sem assinatura do cliente** — a S1-22 é justamente essa mitigação, e está aberta |
| R11 | Cliente piloto desistir no meio | 🟡 Médio | O kickoff (S1-21) ainda não aconteceu, e a S1 é a sprint das semanas 2-3 |
| R7 | Custo da API do Claude estourar | 🟡 Médio | Ligado ao débito #8: o custo real nunca foi medido, porque a validação usou modelo local |

---

*Snapshot gerado a partir do estado do repositório em 14/08/2026. Números conferidos contra os checkboxes de `sprints/*.md`, o código em `apps/`, `config/` e `infra/`, e o Oracle 23ai real (`USER_TABLES`, `USER_TRIGGERS`, `USER_CONSTRAINTS`, contagens após `make seed` e `gerar_slots`). O fluxo do chat foi exercitado ponta a ponta contra o Oracle — 19 checagens, dentro de transação revertida ao fim.*

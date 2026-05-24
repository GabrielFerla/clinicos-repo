# Gitflow do ClinicOS

Este documento descreve o fluxo de branches efetivamente praticado no repositório. Para padrões de commits, code style, PRs e ADRs, ver `CONTRIBUTING.md`. Para padrões de nomenclatura de branches de sprint, ver também `CLAUDE.md`.

> **Nota:** o `CONTRIBUTING.md` original descreve um gitflow completo com `develop`, `release/*` e `hotfix/*`. Durante a Sprint 0 ficou claro que, com um único contribuidor e cadência por sprint, o fluxo abaixo (sem `develop`) é suficiente. Quando o time crescer ou existir staging permanente, reintroduzimos `develop` e voltamos ao modelo descrito no `CONTRIBUTING.md`.

## Branches permanentes

| Branch | Função |
|--------|--------|
| `main` | Código de produção / entrega. Protegida: aceita apenas merge via PR. Squash-merge por padrão. |

## Branches efêmeras

| Prefixo | Quando usar | Exemplo |
|---------|-------------|---------|
| `feature/sX-Y-descricao-curta` | Uma branch por tarefa de sprint (`SX-Y` do `sprints/sprint-X-*.md`). | `feature/s1-1-templates-pr-gitflow` |
| `feature/<slug>` | Trabalhos sem código de sprint associado (spikes, scaffolding). | `feature/scaffolding` |
| `fix/<slug>` | Correção de bug encontrado pós-merge, fora de hotfix. | `fix/cpf-validation-edge-case` |
| `hotfix/<slug>` | Correção urgente direto na linha de produção (uso futuro, quando houver ambiente de produção real). | `hotfix/login-loop-prod` |
| `chore/<slug>` | Manutenção sem feature de produto (deps, infra menor, lint). | `chore/bump-django-5.1.4` |
| `docs/<slug>` | Documentação isolada (ADR, plano, escopo). | `docs/adr-0005-tailwind` |

Slugs em **kebab-case**, ASCII, curtos (idealmente 3-5 palavras). Sem acentos.

## Regras de proteção de `main`

`main` é protegida (descoberta na Sprint 0 — o hook bloqueia push direto):

1. **PR obrigatório** — não há push direto, nem `git push origin main`.
2. **Histórico linear** — squash-merge por padrão. Merge commits e rebase-merge devem ser exceção justificada.
3. **CI verde** — quando o pipeline da Sprint 1 estiver no ar (S1-24), `lint + test` precisa passar antes do merge.
4. **CODEOWNERS** — revisão obrigatória dos owners declarados em `.github/CODEOWNERS`.

## Fluxo de uma tarefa de sprint

```text
main
 │
 ├─◀── PR (squash) ──┐
 │                    │
 │              feature/s2-5-crud-medico
 │                    ▲
 │              commits Conventional Commits
 │              com [S2-5] no final
 │
```

Passo a passo:

1. **Sincronizar** local com `main`:
   ```bash
   git checkout main
   git pull --ff-only
   ```
2. **Criar a branch** a partir de `main`:
   ```bash
   git checkout -b feature/s2-5-crud-medico
   ```
3. **Implementar em commits pequenos e descritivos** (Conventional Commits + `[SX-Y]`):
   ```bash
   git commit -m "feat(crm): adiciona modelo Médico [S2-5]"
   ```
4. **Manter a branch limpa antes do PR** (rebase em cima do `main` atualizado):
   ```bash
   git fetch origin
   git rebase origin/main
   ```
5. **Abrir PR** usando `.github/pull_request_template.md`. Preencher DoD, plano de teste e checklist.
6. **Squash-merge** após CI verde e aprovação. Mensagem final do squash deve manter `[SX-Y]` no título.
7. **Marcar `[x]`** no `sprints/sprint-X-*.md` correspondente após o merge.
8. **Apagar a branch** remota e local (o GitHub remove a remota automaticamente quando configurado).

## Hotfix (futuro)

Quando `main` corresponder a um ambiente de produção real:

1. Branch a partir de `main`: `hotfix/<slug>`.
2. PR direto para `main` com label `hotfix` — bypass de revisão demorada, mas ainda exige CI verde.
3. Após merge, criar tag de release patch (`vX.Y.Z+1`).

## Tags e releases

- Releases marcadas com tag `vMAJOR.MINOR.PATCH` em `main` ao final de cada entrega (alinhado com a versão do `ClinicOS_Plano_MVP1.pdf` — ver `CONTRIBUTING.md`, seção *Versionamento*).
- Pré-releases / RCs: `vX.Y.Z-rc.N` quando aplicável.

## O que **não** fazer

- Push direto em `main` (o hook bloqueia; mesmo se passasse, é proibido por política).
- Force-push em branches já em PR aberto sem alinhar com reviewer.
- Branches longevas (> 1 sprint) sem rebase periódico.
- Misturar tarefas de sprints diferentes na mesma branch — uma branch, uma tarefa.

## Referências cruzadas

- `CONTRIBUTING.md` — padrões de commit, code style, PR, testes, ADRs.
- `CLAUDE.md` — modelo orquestrador + subagente para sessões Claude Code.
- `docs/PRE_COMMIT.md` — instalação e uso dos pre-commit hooks (ruff, black, higiene).
- `.github/pull_request_template.md` — template canônico de PR.
- `.github/ISSUE_TEMPLATE/` — templates de issue (bug, feature, sprint task).
- `.github/CODEOWNERS` — donos de revisão.

# Pre-commit hooks — ClinicOS

Este documento explica como instalar e usar os hooks do `pre-commit` configurados em `.pre-commit-config.yaml`. Eles rodam automaticamente antes de cada `git commit` para garantir lint, formatação e higiene mínima dos arquivos.

> O `pre-commit` é **opcional** localmente, mas as mesmas verificações rodam no CI (S1-24). Vale a pena instalar para descobrir problemas antes do push.

## Por que pre-commit?

- **Feedback rápido** — pega problema de estilo/lint em segundos, antes do CI.
- **Consistência** — formatador (black) e linter (ruff) rodam com a mesma versão para todos.
- **LGPD/secrets** — `detect-private-key` bloqueia commit acidental de chaves privadas.
- **Higiene** — normaliza line endings (LF), trailing whitespace, EOF, etc. Já tivemos ruído de CRLF (Windows/WSL) no histórico; o hook `mixed-line-ending` previne isso.

## Hooks ativados

Configurados em [`.pre-commit-config.yaml`](../.pre-commit-config.yaml):

| Hook | Origem | O que faz |
|------|--------|-----------|
| `ruff` | `astral-sh/ruff-pre-commit` | Lint Python com `--fix` (auto-corrige o que dá). Config: `[tool.ruff]` em `pyproject.toml`. |
| `ruff-format` | `astral-sh/ruff-pre-commit` | Apenas verifica formatação ruff (check). Black é quem formata; futuramente pode substituir black. |
| `black` | `psf/black-pre-commit-mirror` | Formatador Python canônico. Config: `[tool.black]` em `pyproject.toml`. |
| `trailing-whitespace` | `pre-commit/pre-commit-hooks` | Remove espaços no fim de linha. Preserva linebreak duplo em `.md`. |
| `end-of-file-fixer` | idem | Garante newline no fim do arquivo. |
| `check-yaml` | idem | Valida sintaxe de arquivos YAML. |
| `check-json` | idem | Valida sintaxe de arquivos JSON. |
| `check-added-large-files` | idem | Bloqueia arquivos > 500 KB no commit. |
| `check-merge-conflict` | idem | Bloqueia marcadores `<<<<<<<` esquecidos. |
| `mixed-line-ending` | idem | Normaliza tudo para LF (`--fix=lf`). |
| `detect-private-key` | idem | Bloqueia chaves SSH/RSA/PGP. **Proteção LGPD.** |

## Instalação

```bash
# 1. Instala o gerenciador (uma única vez, no seu venv ou global)
pip install pre-commit

# 2. Instala o hook git no clone local
pre-commit install
# ou, equivalente:
make hooks-install
```

A partir daqui, todo `git commit` aciona os hooks. Se algum hook falhar, o commit é abortado — corrija e tente de novo.

## Rodar manualmente

```bash
# Roda os hooks em todos os arquivos do repo (útil ao instalar pela 1ª vez):
pre-commit run --all-files

# Roda só um hook específico:
pre-commit run ruff --all-files
pre-commit run black --all-files

# Atualiza as `rev:` dos repos pros tags mais recentes:
pre-commit autoupdate
```

## Pular hooks em emergência

```bash
git commit --no-verify -m "fix(infra): hotfix urgente [S1-25]"
```

> **Atenção:** `--no-verify` só em emergência real (produção fora do ar, deadline imediato). O **CI roda os mesmos hooks**, então pular localmente apenas adia o problema — o PR vai falhar até você consertar e fazer um commit novo.

## Quando um hook quebrar o commit

Comportamento típico:

1. Você roda `git commit`.
2. Ruff/black/etc detectam problemas e **auto-corrigem** os arquivos (apenas reformatam).
3. O commit é **abortado** (porque os arquivos foram modificados).
4. Você roda `git add -u && git commit ...` novamente; agora passa.

Se o hook não auto-corrige (ex.: `check-added-large-files`, `detect-private-key`), você precisa **resolver manualmente** (remover o arquivo, mover para LFS, regenerar a chave, etc.).

## CI x pre-commit

O CI (S1-24) roda `make lint` (ruff + black --check) — equivalente aos hooks do pre-commit nesses dois pontos. Pre-commit local é uma camada extra de proteção contra os outros problemas (line endings, large files, secrets), que o CI também valida em jobs específicos.

## Manutenção

- A cada 1–2 sprints, rode `pre-commit autoupdate` para atualizar as `rev:` dos hooks. Faça em PR isolado (`chore/<slug>`).
- Se um hook novo for adicionado, abra PR com label `chore` e mencione o impacto em `CONTRIBUTING.md` se mudar fluxo do dev.

## Referências

- Página oficial: <https://pre-commit.com/>
- Hooks Python da Astral (ruff): <https://github.com/astral-sh/ruff-pre-commit>
- Hooks genéricos: <https://github.com/pre-commit/pre-commit-hooks>
- Black mirror para pre-commit: <https://github.com/psf/black-pre-commit-mirror>

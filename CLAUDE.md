# ClinicOS — Guia de operação para sessões Claude

Este arquivo é carregado em **toda** sessão de Claude aberta neste repositório. Define como executar tarefas das sprints sem estourar contexto.

## Modelo de execução: orquestrador + subagentes

Você é o **orquestrador**. Quando o usuário pedir *"executa a sprint X"* ou *"implementa SX-Y"*, **NÃO faça a tarefa direto** na sua conversa. **Delegue a um subagente novo** via tool `Agent`.

**Regra de ouro:** `1 tarefa = 1 subagente novo (contexto fresco)`. Isso mantém seu contexto leve mesmo executando 30 tarefas em sequência.

## Fluxo para executar uma sprint inteira

1. **Ler** `sprints/sprint-X-*.md` (você mesmo, no orquestrador) para identificar todas as tarefas `- [ ] SX-Y ...`.
2. **Mapear dependências** — algumas tarefas dependem de outras (S1-5 precisa do S1-2 pronto). Liste em ordem.
3. **Agrupar** tarefas independentes em blocos paralelos.
4. **Para cada bloco**, lance os subagentes em **paralelo** (mesma resposta, múltiplas chamadas de `Agent`).
5. **Espere os resumos**, marque os `[x]` no `.md`, siga para o próximo bloco.
6. **No final**, gere um relatório curto para o usuário: o que foi feito, o que pulou e por quê, sugestão de PR.

## Prompt padrão de subagente

Cada chamada `Agent` (`subagent_type: general-purpose`) deve ter um prompt **auto-contido** — o subagente não vê sua conversa:

```
Implementa a tarefa SX-Y do ClinicOS.

Arquivo da sprint: sprints/sprint-X-<slug>.md (lê para entender o DoD da SX-Y).
Documentos de contexto que pode precisar: docs/ARQUITETURA.md, docs/adr/, CONTRIBUTING.md.

O que fazer:
1. Lê a sprint e identifica os requisitos exatos da SX-Y.
2. Implementa os arquivos necessários.
3. Roda `make test` (ou `make lint` se for tarefa de qualidade).
4. Se quebrar, conserta. No máximo 2 tentativas; se ainda falhar, reporta bloqueador.
5. Commita seguindo Conventional Commits do CONTRIBUTING.md, incluindo [SX-Y] no fim.

Retorna em até 150 palavras:
(a) o que foi feito (arquivos tocados)
(b) commit hash
(c) testes que rodou e resultado
(d) bloqueadores, se houve
```

## Quando parar e perguntar ao usuário

- Subagente reportou bloqueador (teste persistindo em vermelho, dependência ausente, ambiguidade no DoD).
- Escolha arquitetural não documentada em ADR — peça para o usuário decidir antes de inventar.
- Sprint inteira terminada — apresenta resumo e pergunta se deve abrir PR.

## Padrões do projeto (consulte antes de delegar)

- **Branches**: `feature/sX-Y-descricao-curta` (ver `CONTRIBUTING.md`)
- **Commits**: Conventional Commits + `[SX-Y]` no fim — ex.: `feat(crm): adiciona modelo Médico [S2-5]`
- **Code style**: Black + Ruff. Rode `make fmt` antes de commitar.
- **Testes**: pytest, 70% mínimo nos módulos de domínio. Sem cobrir migrations e admin gerado.
- **SQL/Oracle**: UPPER_SNAKE_CASE em tabelas/colunas; toda migration com rollback.
- **HTML/Tailwind**: componentes reutilizáveis em `templates/components/`.

## Higiene de contexto

Se você (orquestrador) acumulou ~50 tarefas executadas na mesma sessão, sugira ao usuário `/compact` ou `/clear` antes de atacar a próxima sprint. Isso libera espaço para os próximos resumos.

## Comandos úteis (todos pré-aprovados em `.claude/settings.json`)

| Comando       | O que faz                                  |
|---------------|--------------------------------------------|
| `make up`     | Sobe Oracle 23ai + Redis + Mailhog          |
| `make down`   | Derruba os serviços                         |
| `make logs`   | Logs dos serviços                           |
| `make test`   | pytest                                      |
| `make lint`   | ruff + black --check                        |
| `make fmt`    | ruff --fix + black                          |
| `make app`    | django runserver (válido após Sprint 1)     |
| `make worker` | celery worker (válido após Sprint 1)        |

# Contribuindo com o ClinicOS

Este documento define o workflow de trabalho no repositório. Vale para o desenvolvedor solo e para qualquer pessoa que entre no projeto depois.

## Gestão de tarefas

As tarefas vivem nos arquivos de sprint em `sprints/`. Cada tarefa tem um código no formato `S{sprint}-{numero}` (ex: `S2-5`).

Conforme as tarefas são concluídas, marque o checkbox no markdown:

```diff
- - [ ] S2-5 Admin: CRUD de Médico (CRM, RQE, especialidades, foto)
+ - [x] S2-5 Admin: CRUD de Médico (CRM, RQE, especialidades, foto)
```

Cada tarefa relevante vira uma **issue no GitHub** com o código da tarefa no título. Exemplo: `[S2-5] Admin: CRUD de Médico`.

## Branches

Padrão **gitflow simplificado**:

- `main` — código em produção, protegido, só recebe merge via PR de `develop`
- `develop` — integração contínua, base para feature branches
- `feature/S{X}-{Y}-descricao-curta` — uma branch por tarefa de sprint
- `hotfix/descricao-curta` — correções emergenciais em produção
- `release/v{X}.{Y}` — preparação de releases

Exemplo de feature branch: `feature/S2-5-crud-medico`.

## Commits

Padrão **Conventional Commits**:

```
feat(agenda): adiciona geração automática de slots semanais [S3-3]
fix(chatbot): corrige tool buscar_slots retornando slot ocupado [S5-5]
docs(adr): registra decisão sobre provedor de embeddings (ADR-0004)
test(crm): adiciona testes de feature para CRUD de paciente [S2-12]
refactor(prontuario): extrai lógica de hash para service dedicado
chore(deps): atualiza django para 5.1.4
```

Prefixos válidos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `style`.

Sempre incluir o código da tarefa entre colchetes quando aplicável.

## Pull Requests

Toda mudança em `develop` ou `main` passa por PR. Template básico:

```markdown
## O que foi feito
[descrição objetiva]

## Tarefas relacionadas
- Closes #42 (S2-5)

## Como testar
[passos]

## Definition of Done desta tarefa
- [ ] Critério 1 do DoD da sprint
- [ ] Critério 2 do DoD da sprint
- [ ] Testes passando localmente
- [ ] CI verde
```

PRs precisam de pelo menos uma aprovação se o time tiver mais de uma pessoa. Em projeto solo, auto-review com pelo menos 24h de distância da implementação.

## Decisões arquiteturais

Toda decisão arquitetural relevante vira um ADR em `docs/adr/`. Vale a regra:

> Se em 6 meses alguém vai perguntar "por que escolheram X em vez de Y?", então escreva um ADR.

Padrão de nome: `NNNN-titulo-descritivo.md` (numeração sequencial). Use o template em `docs/adr/README.md`.

## Code style

Python:
- Formatador: **Black** (configuração padrão)
- Linter: **Ruff**
- Type hints obrigatórios em funções públicas
- Docstrings no formato Google

HTML/Tailwind:
- Classes Tailwind agrupadas: layout → espaçamento → tipografia → cores → estado
- Componentes reutilizáveis em `templates/components/`

SQL/Oracle:
- Nomes de tabelas e colunas em UPPER_SNAKE_CASE (padrão Oracle)
- Comentários em PL/SQL explicando triggers e procedures
- Sempre incluir comando de rollback junto da migration

## Testes

- **Unitários**: lógica isolada, sem banco. `pytest` com mocks.
- **Feature**: views e fluxos completos, com banco de testes Oracle.
- **E2E**: fluxos críticos do usuário com Playwright.
- **Adversariais**: chatbot recebendo prompt injection, sycophancy, etc.

Cobertura mínima: 70% nos módulos de domínio. Não cobrir migrations e admin gerado.

## Documentação

- Mudanças no escopo → atualizar `docs/ESCOPO.md` e gerar nova versão do PDF
- Decisões → ADR
- Riscos novos → atualizar `docs/RISCOS.md`
- Métricas → atualizar `docs/METRICAS.md` com dados reais após go-live

## Versionamento

O PDF `ClinicOS_Plano_MVP1.pdf` é regerado ao final de cada sprint a partir destes MDs. Versões marcadas como `1.0`, `1.1`, `1.2`... formam o histórico de evolução do plano. Não editar o PDF diretamente.

## Comunicação com cliente piloto

- Reuniões quinzenais ao final de cada sprint (review + planning)
- Demos sempre em ambiente de staging, nunca em localhost
- Toda mudança de escopo solicitada vira issue marcada como `escopo-mvp2`, nunca entra na sprint corrente

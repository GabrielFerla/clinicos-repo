<!--
Obrigado por contribuir com o ClinicOS!
Preencha as seções abaixo. Itens que não se aplicam podem ser marcados como N/A.
Convenção de título do PR (Conventional Commits): `tipo(escopo): descrição curta [SX-Y]`
Exemplo: `feat(crm): adiciona modelo Médico [S2-5]`
-->

## Resumo

<!-- 1-3 frases sobre o "porquê" desta mudança. Foque no impacto no usuário/sistema. -->

## Sprint / Tarefa

- Sprint: `Sprint X`
- Tarefa: `SX-Y` — <título curto>
- Issue relacionada: `Closes #<numero>` (se houver)

## Definition of Done

<!-- Cole aqui os itens do DoD desta tarefa (de `sprints/sprint-X-*.md`) e marque os concluídos. -->

- [ ] Critério 1 do DoD da tarefa
- [ ] Critério 2 do DoD da tarefa
- [ ] (adicionar conforme a sprint)

## Checklist do autor

- [ ] Código segue Black + Ruff (`make fmt` rodado localmente)
- [ ] `make lint` passa sem erros
- [ ] `make test` passa localmente
- [ ] Cobertura de testes mantida >= 70% nos módulos de domínio tocados
- [ ] Migrations Oracle incluem comando de rollback (se aplicável)
- [ ] Nomes de tabelas/colunas em UPPER_SNAKE_CASE (se aplicável)
- [ ] Documentação atualizada (`docs/ARQUITETURA.md`, `docs/ESCOPO.md`, `docs/METRICAS.md`, etc.) se aplicável
- [ ] ADR criado em `docs/adr/` se houve decisão arquitetural relevante
- [ ] Branch nomeada como `feature/sX-Y-descricao-curta` (ou `fix/...` / `hotfix/...`)
- [ ] Commits seguem Conventional Commits com `[SX-Y]` no final
- [ ] Variáveis sensíveis (CPF, segredos) não foram logadas nem commitadas

## Plano de teste

### Manual

<!-- Passos para reproduzir localmente o que o PR entrega. Ex.: -->
1. `make up`
2. `make app`
3. Acessar `http://localhost:8000/...`
4. Observar comportamento X

### Automatizado

<!-- Comandos pytest específicos e/ou fixtures relevantes. -->
```bash
make test
# ou: pytest apps/<modulo>/tests/ -v
```

## Screenshots / GIFs (se UI)

<!-- Arraste imagens aqui. Antes/depois quando aplicável. -->

## Riscos e impacto

<!-- Algum risco de regressão? Migration destrutiva? Mudança em contrato de API? -->

## Notas para o reviewer

<!-- Pontos de atenção, dúvidas em aberto, decisões deliberadas que merecem segundo olho. -->

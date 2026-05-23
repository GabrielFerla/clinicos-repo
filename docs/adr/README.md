# Architecture Decision Records (ADRs)

> Registro de decisões arquiteturais relevantes do ClinicOS. Cada ADR captura uma decisão específica, seu contexto e suas consequências.

## Quando criar um ADR

Crie um ADR quando responder "sim" para qualquer destas perguntas:

- Em 6 meses, alguém perguntará "por que escolheram X em vez de Y?"
- A decisão envolve trade-off entre alternativas razoáveis?
- A reversão seria custosa?
- A decisão afeta múltiplos módulos ou camadas?

Não crie ADR para escolhas óbvias ou triviais (ex: "usar HTTPS", "armazenar senhas com hash").

## Padrão de nomenclatura

`NNNN-titulo-descritivo.md`

- `NNNN`: número sequencial, sempre 4 dígitos
- `titulo-descritivo`: kebab-case, curto, descritivo

## Estados de um ADR

- **Proposed** — escrito, em discussão
- **Accepted** — aceito, em vigor
- **Deprecated** — substituído ou abandonado (mas mantido para histórico)
- **Superseded by ADR-NNNN** — substituído por outro ADR específico

## Template

```markdown
# ADR-NNNN: Título descritivo

- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNNN
- **Data:** YYYY-MM-DD
- **Decisor(es):** [nomes]

## Contexto

[Qual problema estamos resolvendo? Qual a situação atual? Quais forças estão em jogo?]

## Alternativas consideradas

### Opção A: [nome]
- Prós: ...
- Contras: ...

### Opção B: [nome]
- Prós: ...
- Contras: ...

## Decisão

[O que decidimos? Qual opção foi escolhida e por quê?]

## Consequências

### Positivas
- ...

### Negativas
- ...

### Neutras / mitigações
- ...

## Notas adicionais

[Links, referências, contexto extra]
```

---

## Índice de ADRs

| # | Título | Status | Data |
|---|---|---|---|
| [0001](0001-banco-oracle-23ai.md) | Banco de dados: Oracle 23ai | ✅ Accepted | 2026-05-17 |
| [0002](0002-django-em-vez-de-laravel.md) | Backend: Django em vez de Laravel | ✅ Accepted | 2026-05-17 |
| [0003](0003-htmx-sem-vue.md) | Frontend: HTMX + Alpine.js, sem Vue | ✅ Accepted | 2026-05-17 |
| [0004](0004-provedor-embeddings.md) | Provedor de embeddings | 🟡 Proposed | 2026-05-17 |

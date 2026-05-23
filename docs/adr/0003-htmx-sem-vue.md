# ADR-0003: Frontend — HTMX + Alpine.js, sem Vue.js

- **Status:** ✅ Accepted
- **Data:** 2026-05-17
- **Decisor(es):** Dev lead

## Contexto

Surgiu a proposta inicial de usar **Vue.js** para o frontend, com a preocupação de que sem framework JavaScript moderno o sistema teria "interface feia" — especialmente o painel dos médicos.

A reavaliação considera:

1. O dev não conhece Vue.js (aprenderia do zero)
2. Já está aprendendo Django, Oracle 23ai, Anthropic SDK, Vector Search
3. Cronograma é de 13 semanas
4. A maior parte das telas é CRUD (Django Admin cobre)
5. As partes interativas (chatbot, calendário) podem ser resolvidas sem SPA

A pergunta real: **Vue agrega valor proporcional ao custo de adicioná-lo?**

## Alternativas consideradas

### Opção A: Django + Vue SPA separados (DRF + Vue)
- **Prós:**
  - Frontend ultra-flexível
  - SPA tradicional, paradigma conhecido na indústria
- **Contras:**
  - **Perde o Django Admin** como CRM pronto
  - Autenticação, CORS, refresh tokens = horas perdidas
  - Dois deploys, duas pipelines
  - Cada tela = endpoint DRF + serializer + componente Vue + roteamento
  - **Triplica o trabalho** em um projeto com cronograma apertado
  - Curva: aprender Vue + Pinia + Vue Router + Vite

### Opção B: Django + Vue como "ilhas" (componentes pontuais)
- **Prós:**
  - Mantém Django Admin como CRM
  - Permite interatividade rica onde for necessário
- **Contras:**
  - Ainda precisa de build step, npm, Vite
  - Ainda precisa aprender Vue básico
  - Comunicação Django ↔ Vue exige cuidado
  - Adiciona complexidade que provavelmente não será aproveitada

### Opção C: Django + HTMX + Alpine.js
- **Prós:**
  - **Zero build step** — escreve HTML, anota com atributos `hx-*`, funciona
  - HTMX resolve a maior parte do que SPAs resolvem (chat, busca live, formulários dinâmicos)
  - Alpine.js cobre os 10% restantes (dropdowns, modais, validação inline)
  - **Streaming via SSE** + HTMX = chat moderno sem 1 linha de framework JS
  - Coerência total com Django — server-side rendering
  - Curva de aprendizado de horas, não semanas
- **Contras:**
  - Menos prestígio "moderno" do que Vue/React (importa pouco para a banca)
  - Limitações em UI muito complexa (não é o caso)

## Decisão

**Adotar Django Templates + HTMX + Alpine.js, sem Vue.**

A regra: começar sem Vue e adicionar **só** se HTMX não resolver. Não há sinal de que isso aconteça neste MVP.

## Consequências

### Positivas
- Cronograma de 13 semanas vira realista em vez de apertado
- Stack único de renderização (server-side), menos contexto switching
- Sem build, sem npm em produção, deploy mais simples
- Django Admin como CRM completo, com django-unfold dando o visual moderno
- Chat com streaming funciona com SSE + HTMX em menos código que com Vue
- Foco do tempo escasso vai para o que importa: IA, Oracle, lógica de domínio

### Negativas
- Em telas hipoteticamente muito complexas (futuro, talvez), pode ser preciso introduzir framework JS — mas isso é um problema futuro
- Recrutamento de devs no futuro pode estranhar a escolha (HTMX ainda é nicho)

### Neutras / mitigações
- Se em algum momento HTMX começar a doer, **adicionamos Vue como ilhas** sem refazer o sistema
- Site responsivo via Tailwind cobre mobile sem necessidade de app
- Beleza visual vem de **design + Tailwind + django-unfold**, não de framework JS

## Notas adicionais

> "Beleza de interface vem de design + CSS bem feito, não do framework JavaScript."

Exemplos públicos:
- HEY.com (HTMX + Hotwire) — interface refinadíssima sem SPA
- Linear (React, mas o ponto vale) — design system, não framework, faz a diferença
- Django Admin moderno: https://unfoldadmin.com/demo

Referências:
- HTMX: https://htmx.org
- Alpine.js: https://alpinejs.dev
- Streaming SSE com Django + HTMX: pattern documentado, simples de implementar

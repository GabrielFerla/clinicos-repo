# ADR-0002: Backend — Django em vez de Laravel

- **Status:** ✅ Accepted
- **Data:** 2026-05-17
- **Decisor(es):** Dev lead

## Contexto

A primeira versão do plano sugeria **Laravel 11 + Filament + PHP** como stack principal, por familiaridade prévia do desenvolvedor (atualmente trabalha com Laravel profissionalmente).

Ao reavaliar a decisão considerando:

1. Projeto patrocinado pela Oracle (driver oficial é Python)
2. Componentes de IA centrais ao produto (chatbot, embeddings, RAG)
3. Necessidade de CRM interno com baixo esforço de UI
4. Cronograma apertado (13 semanas)

…a escolha de framework ganha peso técnico maior do que a familiaridade.

## Alternativas consideradas

### Opção A: Laravel 11 + Filament + PHP 8.3 + python-oracle indireto
- **Prós:**
  - Familiaridade total do desenvolvedor
  - Filament é maduro para CRUD admin
  - Livewire 3 cobre interatividade
- **Contras:**
  - **Driver Oracle** (`yajra/laravel-oci8`) é comunitário, não oficial
  - **Integração com IA** sempre via HTTP para serviços Python (microserviço extra)
  - **Oracle não tem afinidade especial com Laravel** — narrativa fraca para patrocinador
  - **Vector Search** exige workarounds em PHP (sem SDK nativo)

### Opção B: Django 5 + django-unfold + Python 3.12
- **Prós:**
  - **Driver oficial** mantido pela Oracle (`python-oracledb`)
  - **Python é a língua-mãe de IA** — Anthropic SDK, ferramentas de embeddings, frameworks de RAG
  - **Django Admin** customizado com `django-unfold` cobre o CRM interno
  - **Uma linguagem** resolve banco + web + IA (menos overhead mental)
  - **Patrocinador Oracle** vai recomendar este caminho
- **Contras:**
  - **Desenvolvedor não conhece Django** — adiciona curva de aprendizado
  - Django Admin precisa ser customizado para não parecer datado
  - Menos magic do que Laravel em alguns cenários

### Opção C: FastAPI + Frontend separado
- **Prós:**
  - Modernidade e performance
  - API-first natural
- **Contras:**
  - **Sem Admin nativo** — precisa construir CRM do zero
  - Mais código, mais manutenção, mais tempo
  - Cronograma de 13 semanas não comporta

## Decisão

**Adotar Django 5 + Python 3.12 + django-unfold.**

Justificativa decisiva: o projeto tem **três centros de gravidade** — Oracle, IA, e CRM interno. Python + Django é o único stack que serve aos três com fricção mínima:

- **Oracle:** driver oficial, suporte completo a 23ai incluindo Vector Search
- **IA:** ecossistema Python tem o melhor suporte para Anthropic SDK, embeddings, processamento de dados
- **CRM:** Django Admin com tema moderno é gratuito em horas de trabalho

O custo (aprender Django) é absorvido pela Sprint 0 e parte da Sprint 1.

## Consequências

### Positivas
- Eliminação do microserviço Python separado (que existiria com Laravel)
- Stack unificado, menos peças móveis, deploy mais simples
- Django Admin como CRM = enorme economia de tempo na Sprint 2
- Documentação Django é referência da indústria, facilita o aprendizado
- Habilidade de carreira útil (Django + Python é altamente demandado)

### Negativas
- Curva de aprendizado: dev precisa estudar Django ao longo das Sprints 0-1
- Templates Django ≠ Blade; mudança de muscle memory
- ORM do Django tem peculiaridades diferentes do Eloquent

### Neutras / mitigações
- Sprint 0 inclui tempo dedicado a tutorial Django oficial
- Material em português para Django é abundante
- Concept de "fat services / thin views" será mantido como no Laravel

## Notas adicionais

- Familiaridade prévia com Laravel **não é desperdiçada**: muitos conceitos (ORM, migrations, queue, ORM relationships) são análogos.
- django-unfold demo: https://unfoldadmin.com
- Decisão reforçada pelo fato de o ChatService precisar de Tool Use, que tem SDK Python first-class.

# Sprint 0 — Validação técnica

**Duração:** 1 semana · 15–25h
**Período:** Semana 1
**Status:** ☐ Pendente

## Meta

> Provar que a stack funciona ponta a ponta antes de escrever uma linha do produto real. **Código descartável** — viver em repositório separado (`clinicos-spike`).

---

## Por que esta sprint existe

A maior parte dos projetos que falham descobrem incompatibilidades técnicas tarde demais, quando refazer custa caro. Esta sprint vale R$ 0 em código de produto mas vale **certeza** sobre cada peça da stack. Se algum checkpoint falhar aqui, decidimos cedo e barato.

---

## Tarefas

### Checkpoint 1: Oracle 23ai Free no Docker
- [ ] **S0-1** Subir container Oracle 23ai Free via Docker · **DEVOPS** · 2h
- [ ] **S0-2** Conectar com DBeaver e validar `SELECT 'hello' FROM dual` · **DEVOPS** · 1h
- [ ] **S0-3** Criar tabela teste, inserir 100 linhas, validar persistência · **DEVOPS** · 1h

### Checkpoint 2: Django + Oracle
- [ ] **S0-4** Criar projeto Django mínimo · **BACK** · 1h
- [ ] **S0-5** Instalar e configurar `python-oracledb` em thin mode · **BACK** · 1h
- [ ] **S0-6** Configurar `DATABASES` no settings apontando para Oracle 23ai · **BACK** · 1h
- [ ] **S0-7** Criar model `PacienteSpike` com `CharField`, `IntegerField`, `DateTimeField` · **BACK** · 0.5h
- [ ] **S0-8** Rodar `makemigrations` + `migrate` e validar tabela no Oracle via DBeaver · **BACK** · 1h
- [ ] **S0-9** Criar paciente via shell Django, validar UTF-8 com caractere acentuado · **BACK** · 0.5h

### Checkpoint 3: Vector Search no Oracle 23ai
- [ ] **S0-10** Criar tabela `FAQ_SPIKE` com coluna `VECTOR(1024, FLOAT32)` · **DB** · 1h
- [ ] **S0-11** Escolher provedor de embedding (preliminar) — testar 1, 2 ou 3 opções · **AI** · 3h
- [ ] **S0-12** Gerar embeddings de 10 FAQs e inserir no Oracle via Python · **AI+DB** · 2h
- [ ] **S0-13** Executar `VECTOR_DISTANCE` com query "Quanto custa?" e validar resultado · **AI+DB** · 1h
- [ ] **S0-14** Criar índice HNSW e medir ganho de performance · **DB** · 1h

### Checkpoint 4: Claude API com Tool Use
- [ ] **S0-15** Instalar `anthropic` SDK Python · **AI** · 0.5h
- [ ] **S0-16** Implementar tool `buscar_horarios_disponiveis` que consulta Oracle · **AI+BACK** · 3h
- [ ] **S0-17** Conversar com Claude no terminal, validar grounding · **AI** · 1h
- [ ] **S0-18** Testar caso adversarial: perguntar por especialidade que não existe · **AI** · 0.5h

### Checkpoint 5: Django Admin com django-unfold
- [ ] **S0-19** Instalar `django-unfold` e configurar tema · **FRONT** · 1h
- [ ] **S0-20** Cadastrar Paciente via Admin, validar visual moderno · **FRONT** · 0.5h
- [ ] **S0-21** Decisão registrada: Django Admin é suficiente para o CRM? · **FRONT+DESIGN** · 0.5h

### Checkpoint 6: Chat HTMX com streaming
- [ ] **S0-22** Configurar HTMX e Alpine.js no template Django · **FRONT** · 1h
- [ ] **S0-23** View Django retornando SSE de mensagem teste (sem IA) · **FRONT+BACK** · 2h
- [ ] **S0-24** Integrar com Claude API streaming, mostrar tokens chegando ao navegador · **FRONT+AI** · 2h

### Documentação e decisões
- [ ] **S0-25** Atualizar `ADR-0004` com a decisão final sobre embeddings · **AI** · 1h
- [ ] **S0-26** Criar README em cada pasta de checkpoint do `clinicos-spike` · **TODOS** · 1h
- [ ] **S0-27** Apresentar resultados para orientador e patrocinador (informal) · **TODOS** · 1h

---

## Definition of Done

- [ ] Repositório `clinicos-spike` criado (separado do `clinicos`) com 6 pastas
- [ ] Cada pasta tem README curto descrevendo o que foi provado e como rodar
- [ ] `ADR-0004` atualizado com a decisão final sobre provedor de embeddings
- [ ] Nenhum bloqueador técnico desconhecido restante para iniciar a Sprint 1
- [ ] Se algum checkpoint falhar: ADR adicional registrando o problema e o plano B

---

## Demos da review

Mostrar ao orientador / patrocinador:

1. **Oracle rodando** com tabela criada via Django Admin (validação visual)
2. **Vector Search funcionando** — terminal mostrando query "quanto custa?" retornando "vocês aceitam convênio?" como mais similar
3. **Tool Use funcionando** — Claude no terminal respondendo com horário real do banco
4. **Chat streaming** — navegador mostrando tokens aparecendo um a um

Roteiro de 10 minutos. Sem PowerPoint.

---

## O que NÃO fazer nesta sprint

Vital evitar tentações:

- ❌ Estilizar com Tailwind
- ❌ Modelar o schema final
- ❌ Organizar em apps Django
- ❌ Escrever testes
- ❌ Configurar Celery/Redis
- ❌ Deploy
- ❌ Começar a tela bonita do site

Tudo isso é Sprint 1+.

---

## Notas

> Espaço livre para anotações durante a execução. Substituir este texto pelas descobertas reais.

_(nenhuma nota ainda)_

---

## Riscos específicos desta sprint

- **R2** (driver Oracle) — se materializar aqui, vira problema imediato. Plano B em ADR-0001.
- **R3** (Vector Search via Python) — Checkpoint 3 é o teste decisivo. Se falhar, atualizar ADR-0004 com workaround.

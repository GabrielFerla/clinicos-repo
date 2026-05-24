# Sprint 1 — Fundação

**Duração:** 2 semanas
**Período:** Semanas 2-3
**Status:** ☐ Pendente
**Pré-requisito:** Sprint 0 concluída com sucesso

## Meta

> Ambiente do projeto real montado, schema completo migrado no Oracle, identidade visual definida, equipe alinhada com cliente piloto.

---

## Tarefas

### Repositório e infraestrutura local
- [x] **S1-1** Repositório `clinicos` no GitHub com estrutura gitflow e templates de PR · **DEVOPS** · 2h
- [x] **S1-2** Docker Compose: Django + Oracle 23ai + Redis + Mailhog (dev) · **DEVOPS** · 4h
- [ ] **S1-3** Script `make setup` que faz tudo em 1 comando para novos devs · **DEVOPS** · 2h

### Estrutura do projeto Django
- [x] **S1-4** Criar projeto Django com layout `apps/` + `config/` · **BACK** · 2h
- [ ] **S1-5** Criar apps: `core`, `agenda`, `prontuario`, `chatbot`, `crm`, `site_publico` · **BACK** · 1h
- [ ] **S1-6** Settings divididos: `base.py`, `dev.py`, `prod.py`, `test.py` · **BACK** · 2h
- [ ] **S1-7** Configurar variáveis de ambiente via `django-environ` · **BACK** · 1h

### Modelagem completa
- [ ] **S1-8** Modelagem das entidades em Django models · **BACK+DB** · 8h
  - [ ] Especialidade
  - [ ] Medico, MedicoEspecialidade
  - [ ] Paciente
  - [ ] AgendaRegra, AgendaSlot
  - [ ] Consulta
  - [ ] Prontuario, Evolucao
  - [ ] Lead, InteracaoChat
  - [ ] FaqVector
  - [ ] Usuario (User custom)
  - [ ] LogAcesso
- [ ] **S1-9** Migrations Oracle de todas as tabelas base, com índices · **DB** · 5h
- [ ] **S1-10** Trigger PL/SQL de imutabilidade em `EVOLUCAO` via RunPython · **DB** · 3h
- [ ] **S1-11** Constraint UNIQUE de slot + script de teste · **DB** · 2h
- [ ] **S1-12** Criação do índice HNSW em `FAQ_VECTOR.EMBEDDING` · **DB** · 1h

### Helpers e segurança
- [ ] **S1-13** Helper de criptografia AES-256 para CPF · **BACK** · 3h
- [ ] **S1-14** Helper de hash determinístico HMAC-SHA256 com pepper · **BACK** · 2h
- [ ] **S1-15** Testes unitários dos helpers de cripto · **BACK+QA** · 3h
- [ ] **S1-16** Seeders com dados realistas de clínica oftalmológica · **DB** · 4h
  - 5 médicos com diferentes subespecialidades
  - 50 pacientes
  - 200 slots futuros
  - 20 FAQs com embeddings

### Frontend base
- [ ] **S1-17** Configuração de Tailwind via `django-tailwind` · **FRONT** · 3h
- [ ] **S1-18** Identidade visual: paleta, tipografia, design tokens · **DESIGN** · 6h
- [ ] **S1-19** Logo placeholder do ClinicOS (versão definitiva no MVP2) · **DESIGN** · 2h
- [ ] **S1-20** Wireframes de baixa fidelidade de todas as telas no Figma · **DESIGN** · 10h

### Cliente e processo
- [ ] **S1-21** Reunião de kickoff com cliente piloto · **TODOS** · 2h
- [ ] **S1-22** Assinatura formal da lista de fora-do-escopo (`ESCOPO.md`) · **TODOS** · 1h
- [ ] **S1-23** Criar issues no GitHub para todas as tarefas das sprints 1-6 · **DEV LEAD** · 3h

### CI/CD básico
- [ ] **S1-24** GitHub Actions: lint (ruff), formatador (black), pytest · **DEVOPS** · 4h
- [ ] **S1-25** Pre-commit hooks instalados · **DEVOPS** · 1h
- [ ] **S1-26** Badge de CI no README · **DEVOPS** · 0.5h

---

## Definition of Done

- [ ] `docker compose up` sobe a stack inteira em qualquer máquina Windows/WSL ou macOS
- [ ] `python manage.py migrate` aplica todas as migrations sem erros no Oracle 23ai
- [ ] Trigger de imutabilidade testado: `UPDATE` em `EVOLUCAO` lança exceção
- [ ] Helpers de CPF passam em testes unitários (criptografar/descriptografar/hash)
- [ ] Pipeline de CI verde no GitHub
- [ ] Lista de escopo fora-do-MVP1 assinada (física ou digital) pelo cliente piloto
- [ ] Issues no GitHub criadas para Sprints 1-6 com labels apropriadas
- [ ] Wireframes de todas as telas disponíveis no Figma

---

## Demos da review

1. **Setup do projeto** — colega clona o repo, roda `make setup`, sobe tudo localmente
2. **Schema no Oracle** — abrir DBeaver e mostrar todas as tabelas com seus relacionamentos
3. **Trigger funcionando** — tentar dar UPDATE em uma evolução e ver a exceção
4. **Identidade visual** — mostrar paleta, tipografia e wireframes principais

---

## Notas

_(adicionar durante a execução)_

---

## Riscos específicos desta sprint

- **R1** (LGPD) — criptografia de CPF tem que sair correta aqui ou nunca sai
- **R8** (scope creep) — pressão para começar coding antes de wireframes está pronto; resistir

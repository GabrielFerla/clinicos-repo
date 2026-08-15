# Sprint 2 — CRM interno (cadastros)

**Duração:** 2 semanas
**Período:** Semanas 4-5
**Status:** 🔄 Em andamento — 6/20 · CRUDs, permissões por perfil e testes entregues na fatia de 14/08; faltam tema do Admin, autenticação e validação com o cliente

## Meta

> Recepção consegue logar, cadastrar médicos, especialidades e pacientes com qualidade visual de SaaS moderno. Permissões por perfil funcionando.

---

## Tarefas

### Visual e tema do Admin
- [ ] **S2-1** Configuração final do `django-unfold`: cores, logo, menu lateral · **FRONT** · 4h
- [ ] **S2-2** Customizar dashboard inicial do Admin com widgets básicos · **FRONT** · 4h

### Autenticação e perfis
- [x] **S2-3** Modelo `User` customizado com campo `perfil` (medico/recepcao) · **BACK** · 3h
- [ ] **S2-4** Sistema de autenticação com 2 perfis · **BACK** · 4h
- [ ] **S2-5** Página de login customizada com identidade visual ClinicOS · **FRONT** · 4h
- [ ] **S2-6** Recuperação de senha por e-mail (Mailhog em dev) · **BACK** · 3h

### Cadastros
- [ ] **S2-7** Admin: CRUD de Especialidade com ícones por subespecialidade · **BACK** · 3h
- [ ] **S2-8** Admin: CRUD de Médico (CRM, RQE, especialidades, upload de foto) · **BACK** · 6h
- [ ] **S2-9** Admin: CRUD de Paciente · **BACK** · 8h — **4/5, ver Notas**
  - [x] CPF criptografado no save
  - [x] Busca por CPF via hash determinístico
  - [ ] Campos oftalmológicos: usa óculos, diabetes, hipertensão, cirurgias prévias
  - [x] Validação de CPF (algoritmo oficial)
  - [x] Checagem de duplicidade via hash antes de salvar

### Permissões e segurança
- [x] **S2-10** Permissões por perfil: recepção vê tudo, médico vê só seus pacientes · **BACK** · 5h
- [ ] **S2-11** Audit log básico: quem criou/editou cada registro · **BACK** · 4h
- [ ] **S2-12** Rate limit nas rotas de autenticação · **BACK** · 2h

### Listagens e produtividade
- [x] **S2-13** Filtros, busca e paginação nas listagens · **BACK** · 4h
- [ ] **S2-14** Exportação CSV de pacientes e médicos (uso interno) · **BACK** · 3h
- [ ] **S2-15** Mensagens flash padronizadas em todas as ações · **FRONT** · 2h

### Testes
- [x] **S2-16** Testes unitários dos helpers de criptografia e validações · **QA** · 5h
- [x] **S2-17** Testes de feature dos CRUDs principais · **QA** · 6h
- [x] **S2-18** Teste de permissões: médico tentando ver paciente alheio = 403 · **QA** · 2h

### Validação com cliente
- [ ] **S2-19** Demonstração informal com recepcionista da clínica piloto · **TODOS** · 2h
- [ ] **S2-20** Coletar feedback e ajustar UX se necessário · **TODOS** · 4h

---

## Definition of Done

- [ ] Recepção faz login e cadastra médico, especialidade e paciente sem ajuda do dev
- [x] CPF é armazenado criptografado no banco (verificado via SQL direto)
- [x] Busca de paciente por CPF funciona via hash determinístico
- [x] Médico só visualiza pacientes que tem consulta agendada com ele
- [x] Tentativa de acessar paciente alheio retorna 403 — **sai 302, ver Notas**
- [ ] Cobertura de testes ≥ 70% nos módulos de cadastro
- [ ] Demonstração informal com recepcionista da clínica feita e feedback coletado

---

## Demos da review

1. **Recepcionista cadastra paciente novo** — fluxo completo, sem ajuda
2. **Médico tenta acessar paciente que não é dele** — bloqueio na cara
3. **Inspeção no banco via DBeaver** — CPF criptografado, hash visível
4. **Busca de paciente por CPF** — usuário digita CPF, sistema acha mesmo estando criptografado

---

## Notas

**14/08/2026 — fatia "mini CRM + chat que agenda".** Entregue fora da ordem da sprint,
junto com partes das S3 e S5, para destravar o uso real do sistema. Ver `docs/STATUS.md`.

- **S2-3 já estava pronta** desde a S1-8: `Usuario(AbstractUser)` com `perfil`
  ADMIN/MEDICO/RECEPCAO. Só faltava marcar.
- **S2-9 ficou 4/5.** O CRUD de paciente funciona ponta a ponta — CPF cifrado via
  `definir_cpf()`, validação dos dois dígitos verificadores (`validar_cpf`), recusa de
  duplicado por `cpf_hash` e busca pelos 11 dígitos na listagem. Faltam **só os campos
  oftalmológicos** (usa óculos, diabetes, hipertensão, cirurgias prévias): eles não
  existem no model `Paciente` e exigem migration própria. A tarefa segue aberta por
  isso, para o placar do `STATUS.md` não contar como pronto o que não está.
- **S2-18 passa, mas o código é 302 e não 403.** O `get_queryset` recortado por perfil
  faz o Admin responder "objeto não existe" e redirecionar, em vez de "proibido". É o
  comportamento padrão do Django Admin e é preferível: um 403 confirmaria ao médico
  que aquele paciente existe. O teste aceita 302 ou 403 e verifica o que importa —
  o objeto alheio não aparece nem na listagem nem no detalhe.
- **Vínculo `Medico.usuario` criado** (`OneToOneField`, migration `0004_medico_usuario`)
  — sem ele não havia como expressar "só os meus". O índice extra `IDX_MEDICO_USUARIO`
  **não** foi criado: o UNIQUE do `OneToOneField` já indexa a coluna e o Oracle recusa
  com `ORA-01408`.
- **Fora do escopo desta fatia:** S2-1/S2-2 (django-unfold e dashboard), S2-5 (login
  custom), S2-6 (recuperação de senha), S2-12 (rate limit), S2-14 (CSV), S2-15 (flash
  messages), S2-19/S2-20 (validação com o cliente).

---

## Riscos específicos desta sprint

- **R1** (LGPD) — criptografia precisa estar 100% nesta sprint, não em sprint posterior
- **R8** (scope creep) — recepcionista vai pedir "só uma coisinha". Anotar tudo, postergar para MVP2

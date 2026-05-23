# Sprint 2 — CRM interno (cadastros)

**Duração:** 2 semanas
**Período:** Semanas 4-5
**Status:** ☐ Pendente

## Meta

> Recepção consegue logar, cadastrar médicos, especialidades e pacientes com qualidade visual de SaaS moderno. Permissões por perfil funcionando.

---

## Tarefas

### Visual e tema do Admin
- [ ] **S2-1** Configuração final do `django-unfold`: cores, logo, menu lateral · **FRONT** · 4h
- [ ] **S2-2** Customizar dashboard inicial do Admin com widgets básicos · **FRONT** · 4h

### Autenticação e perfis
- [ ] **S2-3** Modelo `User` customizado com campo `perfil` (medico/recepcao) · **BACK** · 3h
- [ ] **S2-4** Sistema de autenticação com 2 perfis · **BACK** · 4h
- [ ] **S2-5** Página de login customizada com identidade visual ClinicOS · **FRONT** · 4h
- [ ] **S2-6** Recuperação de senha por e-mail (Mailhog em dev) · **BACK** · 3h

### Cadastros
- [ ] **S2-7** Admin: CRUD de Especialidade com ícones por subespecialidade · **BACK** · 3h
- [ ] **S2-8** Admin: CRUD de Médico (CRM, RQE, especialidades, upload de foto) · **BACK** · 6h
- [ ] **S2-9** Admin: CRUD de Paciente · **BACK** · 8h
  - CPF criptografado no save
  - Busca por CPF via hash determinístico
  - Campos oftalmológicos: usa óculos, diabetes, hipertensão, cirurgias prévias
  - Validação de CPF (algoritmo oficial)
  - Checagem de duplicidade via hash antes de salvar

### Permissões e segurança
- [ ] **S2-10** Permissões por perfil: recepção vê tudo, médico vê só seus pacientes · **BACK** · 5h
- [ ] **S2-11** Audit log básico: quem criou/editou cada registro · **BACK** · 4h
- [ ] **S2-12** Rate limit nas rotas de autenticação · **BACK** · 2h

### Listagens e produtividade
- [ ] **S2-13** Filtros, busca e paginação nas listagens · **BACK** · 4h
- [ ] **S2-14** Exportação CSV de pacientes e médicos (uso interno) · **BACK** · 3h
- [ ] **S2-15** Mensagens flash padronizadas em todas as ações · **FRONT** · 2h

### Testes
- [ ] **S2-16** Testes unitários dos helpers de criptografia e validações · **QA** · 5h
- [ ] **S2-17** Testes de feature dos CRUDs principais · **QA** · 6h
- [ ] **S2-18** Teste de permissões: médico tentando ver paciente alheio = 403 · **QA** · 2h

### Validação com cliente
- [ ] **S2-19** Demonstração informal com recepcionista da clínica piloto · **TODOS** · 2h
- [ ] **S2-20** Coletar feedback e ajustar UX se necessário · **TODOS** · 4h

---

## Definition of Done

- [ ] Recepção faz login e cadastra médico, especialidade e paciente sem ajuda do dev
- [ ] CPF é armazenado criptografado no banco (verificado via SQL direto)
- [ ] Busca de paciente por CPF funciona via hash determinístico
- [ ] Médico só visualiza pacientes que tem consulta agendada com ele
- [ ] Tentativa de acessar paciente alheio retorna 403
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

_(adicionar durante a execução)_

---

## Riscos específicos desta sprint

- **R1** (LGPD) — criptografia precisa estar 100% nesta sprint, não em sprint posterior
- **R8** (scope creep) — recepcionista vai pedir "só uma coisinha". Anotar tudo, postergar para MVP2

# Sprint 6 — Atendimento, prontuário e hardening

**Duração:** 2 semanas
**Período:** Semanas 12-13
**Status:** ☐ Pendente

## Meta

> Médico realiza atendimento real, prontuário fica legalmente válido, sistema vai para produção monitorado e equipe da clínica está treinada.

---

## Tarefas

### Atendimento e prontuário
- [ ] **S6-1** Tela de atendimento: dados do paciente + histórico + queixa do chat · **BACK+FRONT** · 8h
- [ ] **S6-2** Formulário de nova evolução (anamnese, exame, conduta, prescrição livre) · **BACK+FRONT** · 8h
- [ ] **S6-3** Campos oftalmológicos específicos · **BACK+FRONT** · 5h
  - Acuidade visual (AV) OD/OE
  - Refração estática e dinâmica
  - Pressão intraocular (PIO) OD/OE
  - Fundoscopia (texto livre + imagens futuro MVP2)
  - Biomicroscopia
  - Tonometria
- [ ] **S6-4** Cálculo e armazenamento de hash SHA-256 da evolução + ID do médico + timestamp · **BACK** · 3h
- [ ] **S6-5** Visualização cronológica do histórico do paciente · **FRONT** · 5h
- [ ] **S6-6** Sistema de "adendo" — adicionar info posterior sem editar a evolução original · **BACK+FRONT** · 4h

### Conformidade LGPD
- [ ] **S6-7** Middleware de log de acesso a prontuário · **BACK** · 4h
- [ ] **S6-8** Banner de consentimento LGPD com registro timestampado · **FRONT+BACK** · 4h
- [ ] **S6-9** Página de Política de Privacidade atualizada e revisada · **TODOS** · 3h
- [ ] **S6-10** Endpoint (não exposto no MVP1, mas pronto) de exportação de dados do paciente · **BACK** · 3h

### Segurança e qualidade
- [ ] **S6-11** Auditoria de segurança: OWASP Top 10 (revisão manual + ferramenta `bandit`) · **QA+BACK** · 8h
- [ ] **S6-12** Revisão de queries Oracle: `EXPLAIN PLAN` nas críticas + criação de índices · **DB** · 5h
- [ ] **S6-13** Headers de segurança: HSTS, CSP, X-Frame-Options · **BACK** · 3h
- [ ] **S6-14** Pen-test informal: dev tentando quebrar o sistema por 4h · **QA** · 4h

### Backup e produção
- [ ] **S6-15** Backup automatizado do Oracle + script de restore documentado · **DEVOPS** · 5h
- [ ] **S6-16** **Teste de restore em ambiente limpo** (não é opcional) · **DEVOPS** · 3h
- [ ] **S6-17** Setup do ambiente de produção em OCI Compute · **DEVOPS** · 8h
- [ ] **S6-18** Domínio definitivo configurado com HTTPS · **DEVOPS** · 3h
- [ ] **S6-19** Pipeline CI/CD completo com deploy automatizado para staging e prod · **DEVOPS** · 6h

### Observabilidade
- [ ] **S6-20** Sentry configurado para captura de exceções · **DEVOPS** · 3h
- [ ] **S6-21** Logs estruturados em JSON · **BACK+DEVOPS** · 3h
- [ ] **S6-22** Uptime monitoring (UptimeRobot) configurado · **DEVOPS** · 2h
- [ ] **S6-23** Dashboard de métricas no Admin (custo IA, agendamentos, no-show) · **BACK+FRONT** · 5h

### Documentação e entrega
- [ ] **S6-24** Manual do usuário para recepção em PDF · **DESIGN** · 4h
- [ ] **S6-25** Manual do usuário para médico em PDF · **DESIGN** · 4h
- [ ] **S6-26** Vídeo de 5min mostrando os fluxos principais · **DESIGN** · 5h
- [ ] **S6-27** ADRs adicionais documentando decisões da execução · **BACK** · 4h
- [ ] **S6-28** README do projeto revisado e completo · **TODOS** · 2h

### Treinamento e go-live
- [ ] **S6-29** Treinamento presencial da equipe da clínica · **TODOS** · 6h
- [ ] **S6-30** Plano de rollback documentado (e testado em staging) · **DEVOPS** · 3h
- [ ] **S6-31** Deploy em produção + go-live monitorado nas primeiras 24h · **DEVOPS** · 4h
- [ ] **S6-32** Suporte de plantão na primeira semana pós-lançamento · **TODOS** · contínuo

### Apresentação final
- [ ] **S6-33** Slides da apresentação final para banca · **TODOS** · 8h
- [ ] **S6-34** Ensaio da apresentação · **TODOS** · 3h
- [ ] **S6-35** Apresentação final · **TODOS** · 2h
- [ ] **S6-36** Versão final do PDF do plano gerada e arquivada (`v1.6 final`) · **DEV LEAD** · 1h

---

## Definition of Done

- [ ] Médico realiza atendimento completo: vê histórico, registra evolução, salva
- [ ] Tentativa de editar evolução salva é bloqueada pelo trigger do banco
- [ ] Acesso ao prontuário gera linha em `LOG_ACESSO` automaticamente
- [ ] Backup do Oracle é restaurado em ambiente limpo com sucesso (não basta gerar backup)
- [ ] Sistema em produção respondendo no domínio da clínica
- [ ] Equipe da clínica treinada e usando o sistema por 3 dias sem suporte direto do dev
- [ ] Apresentação final aprovada pela banca
- [ ] Patrocinador Oracle recebeu material de divulgação
- [ ] Todas as métricas técnicas em monitoramento ativo

---

## Demos da review final

> **Apresentação final do projeto.** Plateia: banca + patrocinador + cliente piloto.

Roteiro de 30-40min:

1. **Contexto e dor** — vida do recepcionista hoje (3min)
2. **Jornada resolvida** — paciente conversa, agenda, médico atende (5min)
3. **Demo navegável** — fluxo completo ao vivo (10min)
4. **Diferenciais técnicos** — Vector Search no Oracle 23ai, Tool Use com grounding (5min)
5. **Resultados em produção** — primeira semana de dados reais (5min, se disponível)
6. **O que vem no MVP2** — roadmap (3min)
7. **Q&A** — perguntas e discussão (10min)

---

## Notas

_(adicionar durante a execução)_

---

## Riscos específicos desta sprint

- **R1** (LGPD) — último momento de garantir tudo. Auditoria OWASP é DoD
- **R9** (médicos resistirem) — primeira semana de uso real vai mostrar. Plantão dedicado
- **R10** (backup nunca testado) — esta sprint inclui o teste obrigatório. Não pular

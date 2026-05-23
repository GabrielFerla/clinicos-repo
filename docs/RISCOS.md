# Registro de Riscos — ClinicOS MVP1

> Documento vivo. Riscos novos surgem durante a execução e devem ser adicionados aqui. Riscos resolvidos devem ser marcados como `RESOLVIDO` com data e nota explicando o que mudou.

**Versão:** 1.0 · Maio de 2026

---

## Legenda

| Impacto | Significado |
|---|---|
| 🔴 Crítico | Compromete entrega do MVP1. Tratamento imediato obrigatório |
| 🟠 Alto | Pode atrasar significativamente ou degradar qualidade. Mitigação ativa |
| 🟡 Médio | Causa retrabalho ou frustração. Mitigação planejada |
| 🟢 Baixo | Vigiar. Mitigação eventual |

| Status | Significado |
|---|---|
| 🟢 Ativo | Risco em monitoramento |
| 🟡 Mitigando | Ação em curso |
| ✅ Resolvido | Risco eliminado |
| ❌ Materializou | Virou problema, sendo tratado como incidente |

---

## R1 — LGPD inadequada na entrega final

- **Impacto:** 🔴 Crítico
- **Probabilidade:** Baixa (se seguirmos o plano)
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Log de acesso a prontuário como tarefa obrigatória da Sprint 6
  - Criptografia de CPF como tarefa obrigatória da Sprint 2
  - Banner de consentimento + política de privacidade na Sprint 6
  - Auditoria de segurança OWASP Top 10 antes do go-live
- **Sinal de alerta:** entrar na Sprint 5 sem implementar log de acesso

---

## R2 — Fricção do python-oracledb com features novas do 23ai

- **Impacto:** 🟠 Alto
- **Probabilidade:** Média
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Sprint 0 inteira dedicada a validar o driver antes de qualquer outra coisa
  - Plano B: usar Oracle Stored Procedure quando o driver não der conta
  - Documentar caminhos viáveis em ADR
- **Sinal de alerta:** algum checkpoint da Sprint 0 falhar e o workaround levar mais de 1 dia

---

## R3 — Driver/Oracle incompatível com Vector Search via Python

- **Impacto:** 🟠 Alto
- **Probabilidade:** Baixa-Média
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Validação obrigatória no Checkpoint 3 da Sprint 0
  - Plano B: Oracle Procedure que recebe embedding e retorna IDs
  - Plano C: pgvector em Postgres separado (último recurso, fere patrocínio)
- **Sinal de alerta:** `python-oracledb` não aceitar `VECTOR` no insert ou no select

---

## R4 — Chatbot alucinar horários ou inventar médicos

- **Impacto:** 🟠 Alto
- **Probabilidade:** Média (sem mitigação) / Baixa (com mitigação)
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Toda informação operacional vem de Tool Use, nunca de geração livre
  - Testes adversariais obrigatórios na Sprint 5
  - Validação rigorosa do output do LLM antes de virar dado de sistema
  - System prompt com guardrails explícitos
- **Sinal de alerta:** chatbot mencionar nome de médico que não existe no banco em qualquer teste

---

## R5 — Overbooking por race condition

- **Impacto:** 🟡 Médio
- **Probabilidade:** Alta (sem mitigação) / Muito baixa (com mitigação)
- **Status:** 🟢 Ativo
- **Mitigação:**
  - UNIQUE constraint no banco
  - Transação serializável no momento do agendamento
  - Teste de carga obrigatório na Sprint 3 (100 requests simultâneas)
- **Sinal de alerta:** teste de concorrência não passar na Sprint 3

---

## R6 — Prompt injection no campo de sintoma

- **Impacto:** 🟡 Médio
- **Probabilidade:** Alta (em produção)
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Mensagens do usuário sempre marcadas como `user content`, nunca como instrução
  - System prompt robusto e testado
  - Sanitização de input
  - Testes adversariais com payloads conhecidos
- **Sinal de alerta:** alguém conseguir fazer o bot ignorar o system prompt em testes

---

## R7 — Custo de API do Claude estourar orçamento

- **Impacto:** 🟡 Médio
- **Probabilidade:** Média
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Rate limit por IP (max N conversas/hora)
  - Cache de respostas comuns
  - Monitoramento de custo por turno em produção
  - Usar modelo Haiku quando possível, Sonnet para tool use complexa
  - Orçamento mensal de R$ 200 nos primeiros 3 meses
- **Sinal de alerta:** custo médio por agendamento ultrapassar R$ 0,50 nos testes

---

## R8 — Scope creep durante o desenvolvimento

- **Impacto:** 🟠 Alto
- **Probabilidade:** Alta (sem mitigação) / Média (com mitigação)
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Lista de fora-do-escopo assinada na Sprint 1 (ver `ESCOPO.md`)
  - Toda mudança vira issue marcada como `mudanca-de-escopo` e segue processo formal
  - Reuniões quinzenais com cliente piloto, expectativa alinhada
- **Sinal de alerta:** mais de 2 itens entrando no MVP1 fora da lista original

---

## R9 — Médicos resistirem a digitar prontuário

- **Impacto:** 🟡 Médio
- **Probabilidade:** Alta
- **Status:** 🟢 Ativo
- **Mitigação:**
  - UX simplificado e otimizado para velocidade
  - Queixa pré-preenchida pelo chatbot (médico já abre tela com info pronta)
  - Campos opcionais bem marcados
  - Treinamento presencial na Sprint 6
  - Coletar feedback diário na primeira semana de uso
- **Sinal de alerta:** ≥ 30% das consultas sem evolução registrada nos primeiros 7 dias

---

## R10 — Backup do Oracle nunca testado em restore

- **Impacto:** 🟠 Alto
- **Probabilidade:** Alta (em projetos sem disciplina)
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Sprint 6 inclui **teste de restore obrigatório** em ambiente limpo
  - Backup diário automatizado, retenção de 30 dias
  - Documentação do procedimento de restore
- **Sinal de alerta:** chegada na Sprint 6 sem ter pensado em backup ainda

---

## R11 — Cliente piloto desistir no meio do projeto

- **Impacto:** 🟡 Médio (alto se for tarde, baixo se for cedo)
- **Probabilidade:** Baixa-Média
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Demonstrações ao final de cada sprint
  - Cobrar feedback objetivo e registrar
  - Ter cliente reserva mapeado desde o início (mesmo informal)
  - Manter o cliente "no jogo" com pequenas vitórias frequentes
- **Sinal de alerta:** cliente faltar a 2 reuniões seguidas ou demorar +5 dias para responder

---

## R12 — Banca acadêmica não valorizar features modernas da Oracle

- **Impacto:** 🟢 Baixo (afeta nota, não viabilidade técnica)
- **Probabilidade:** Baixa
- **Status:** 🟢 Ativo
- **Mitigação:**
  - Apresentação dedica bloco específico para Vector Search e justifica academicamente
  - Material adicional para o patrocinador Oracle
  - ADRs bem escritos demonstrando rigor decisório
- **Sinal de alerta:** banca apresentar resistência à escolha do Oracle nas primeiras reuniões

---

## Riscos descobertos durante a execução

> Adicionar aqui novos riscos identificados após a aprovação do plano. Cada um deve seguir o mesmo formato dos anteriores.

_(nenhum registrado ainda)_

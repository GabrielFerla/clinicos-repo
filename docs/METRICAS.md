# Métricas de Sucesso — MVP1

> O MVP1 só é considerado bem-sucedido se estas métricas forem atingidas nos primeiros 30 dias após o go-live na clínica piloto. Sem dados objetivos, não há base para priorizar o MVP2.

**Versão:** 1.0 · Maio de 2026
**Status:** metas definidas, baseline pendente (será coletado na Sprint 6)

---

## Métricas de produto

| Métrica | Meta | O que valida | Como medir |
|---|---|---|---|
| Agendamentos via chatbot | ≥ 40% do total | Canal digital funciona | Contar consultas com `origem=chat` |
| Tempo médio de agendamento via chat | ≤ 3 minutos | UX do chatbot | Diferença entre primeira `INTERACAO_CHAT` e criação da `CONSULTA` |
| Taxa de no-show | ≤ baseline atual + 10% | Confiabilidade do canal | Consultas com `status=nao_compareceu` / total |
| Evoluções registradas | ≥ 90% das consultas atendidas | Adoção pelo médico | `EVOLUCAO` count / `CONSULTA` com `status=atendida` |
| Tempo médio para registrar evolução | ≤ 5 minutos | UX do atendimento | Diferença entre abertura da tela de atendimento e save da evolução |
| Taxa de retorno (consulta de retorno agendada) | ≥ 30% | CRM gera valor | Pacientes com 2+ consultas / pacientes com 1+ consulta |

---

## Métricas técnicas

| Métrica | Meta | O que valida | Como medir |
|---|---|---|---|
| Uptime do sistema | ≥ 99,5% | Estabilidade técnica | UptimeRobot |
| Custo de IA por agendamento | ≤ R$ 0,50 | Sustentabilidade financeira | Soma de tokens das `INTERACAO_CHAT` × custo / agendamentos |
| Tempo médio de resposta da home | ≤ 1,5s | Performance do site | Sentry / Lighthouse |
| Tempo médio de resposta do chatbot (primeiro token) | ≤ 2s | UX do chatbot | Métrica custom no `ChatService` |
| Tempo médio de busca Vector | ≤ 300ms | Performance do Vector Search | Query logging no Oracle |
| Erros não-tratados em produção | ≤ 5 / semana | Qualidade do código | Sentry |
| Tickets de suporte abertos pela clínica | ≤ 5 / semana | Usabilidade real | Registro manual |

---

## Métricas de adoção (qualitativas)

A cada semana após o go-live, conduzir conversa rápida (15min) com:

- 1 médico da clínica
- 1 recepcionista
- Idealmente, 1 paciente que tenha agendado via chat

Perguntas-padrão:

1. O que você usou esta semana que funcionou bem?
2. O que te fez raiva?
3. O que você ainda faz fora do sistema?
4. De 0 a 10, quanto você recomendaria o ClinicOS para outra clínica? Por quê?

Compilar respostas em `docs/feedback/` (não criado neste momento, criar quando começar a fase de operação).

---

## Baseline a coletar antes do go-live

Antes da Sprint 6 (idealmente já na Sprint 5), levantar com a clínica piloto:

- [ ] Volume de consultas/mês hoje
- [ ] Taxa de no-show atual
- [ ] Tempo médio de cadastro de paciente novo (manual)
- [ ] Quantos pacientes retornam em até 12 meses
- [ ] Taxa de erro/duplicação em cadastros atuais
- [ ] Tempo gasto pela recepção em agendamento por telefone

Esses números viram a **linha de base** contra a qual o MVP1 será comparado. Sem baseline, não há "antes e depois" — apenas anedotas.

---

## Cadência de revisão

- **Diariamente (auto)**: dashboard básico no Django Admin com métricas técnicas
- **Semanalmente**: revisão das métricas de produto com cliente piloto
- **Mensalmente**: revisão completa, ajuste de metas, decisão sobre próximas features
- **Após 90 dias**: avaliação final do MVP1, definição do escopo do MVP2

---

## Decisão de Go / No-Go para MVP2

O MVP2 só é iniciado se:

1. **Pelo menos 4 das 6 métricas de produto** estiverem dentro da meta após 30 dias
2. **Cliente piloto sinalizar formalmente** disposição de continuar
3. **Custos operacionais** estiverem dentro do projetado
4. **Banca acadêmica / patrocinador** tiverem aprovado a entrega

Caso contrário, faz-se um ciclo de hardening e iteração sobre o MVP1 antes de escalar para novas features.

# Escopo Funcional — MVP1

> Este documento é a fonte da verdade sobre o que entra e o que **não entra** no MVP1. Toda solicitação fora desta lista vira issue marcada como `escopo-mvp2`.

**Versão:** 1.0 · Maio de 2026
**Status:** aguardando assinatura do cliente piloto

---

## Dentro do escopo (MVP1)

| Cód. | Funcionalidade | Persona | Sprint |
|---|---|---|---|
| **F1** | Site institucional da clínica (landing, especialidades, equipe, contato, FAQ) | Paciente | 4 |
| **F2** | Chatbot público no site com pré-triagem oftalmológica e agendamento | Paciente | 5 |
| **F3** | Catálogo de especialidades oftalmológicas | Paciente / Recepção | 2 |
| **F4** | Cadastro de médicos pela recepção (CRM, RQE, subespecialidades, foto) | Recepção | 2 |
| **F5** | Cadastro de pacientes pela recepção (com CPF criptografado) | Recepção | 2 |
| **F6** | Definição de agenda recorrente por médico + geração automática de slots | Recepção | 3 |
| **F7** | Login para médico e recepção (perfis distintos) | Médico / Recepção | 2 |
| **F8** | Agenda do dia para o médico (consultas ordenadas por horário) | Médico | 3 |
| **F9** | Registro de evolução clínica (append-only, queixa pré-preenchida pelo chat) | Médico | 6 |
| **F10** | Histórico cronológico do paciente | Médico | 6 |
| **F11** | Funil de leads do CRM (chat iniciado → agendado → compareceu → retorno) | Recepção | 5 |
| **F12** | Vector Search no Oracle 23ai para FAQ inteligente da clínica | Paciente (via chatbot) | 5 |
| **F13** | Log de acesso a prontuário (auditoria LGPD) | Sistema | 6 |
| **F14** | E-mail transacional de confirmação e lembrete de consulta | Sistema | 5 |

---

## Fora do escopo (próximas entregas)

Itens explicitamente excluídos do MVP1. Todos foram considerados e adiados por razões estratégicas, não por esquecimento.

### Saúde / clínico

- **Telemedicina** — consultas por vídeo. Requer infra de WebRTC, gravação, conformidade adicional.
- **Prescrição eletrônica** — integração com Memed ou equivalente, assinatura digital.
- **Anexo de exames** — upload de PDFs/imagens diagnósticas, gestão de storage, OCR.
- **Integração com equipamentos diagnósticos** — autorrefrator, tonômetro, OCT, biômetro.
- **Receituário com modelos pré-cadastrados** — biblioteca de prescrições recorrentes.

### Comercial / administrativo

- **Integração com convênios (TISS/TUSS)** — padrão complexo, requer homologação.
- **Faturamento e gestão de recebíveis** — emissão de NFS-e, controle de pagamentos.
- **Dashboards financeiros e relatórios gerenciais** — DRE, fluxo de caixa, KPIs.
- **Distribuição automática de consultas entre médicos** — algoritmo de balanceamento.

### Comunicação

- **Notificações por WhatsApp/SMS** — requer API Business do WhatsApp ou Twilio.
- **Lembretes automáticos D-1 e D-0** — usar e-mail no MVP1, automação no MVP2.
- **Chat ao vivo com atendente humano** — apenas e-mail/telefone como fallback no MVP1.

### Segurança / autenticação

- **MFA por SMS / TOTP / SSO corporativo** — apenas usuário e senha no MVP1.
- **Recuperação de senha por SMS** — apenas por e-mail no MVP1.
- **Assinatura digital ICP-Brasil** — uso de hash da evolução + ID do médico no MVP1.
- **Login do paciente** — paciente não loga no MVP1.

### Infraestrutura / plataforma

- **Aplicativo mobile** — site responsivo cobre o MVP1.
- **Multi-clínica / multi-tenant** — uma clínica piloto, sem isolamento por tenant.
- **API pública** — sem API REST pública no MVP1.
- **Webhooks para integração externa** — fora do MVP1.

---

## Tratamento de mudanças

**Antes da Sprint 1:** mudanças neste escopo são livres e devem ser registradas aqui antes do kickoff.

**Durante a execução (Sprint 1+):** mudanças exigem:

1. Solicitação formal por escrito (issue no GitHub com label `mudanca-de-escopo`)
2. Avaliação de impacto em horas e em sprints afetadas
3. Aprovação do cliente piloto + dev lead
4. Atualização deste documento + regeneração do PDF
5. Versão do PLANO incrementada (1.0 → 1.1)

Solicitações que não atendam todos os critérios viram automaticamente itens do MVP2.

---

## Assinatura

| Papel | Nome | Data | Assinatura |
|---|---|---|---|
| Cliente piloto | _a definir_ | _pendente_ | _pendente_ |
| Dev lead | Gabriel | _pendente_ | _pendente_ |
| Orientador acadêmico | _a definir_ | _pendente_ | _pendente_ |

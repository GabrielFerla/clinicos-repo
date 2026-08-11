# Arquitetura Técnica — ClinicOS

> Detalhes técnicos do MVP1: stack, modelo de dados, decisões críticas, padrões de código. Para entender o **porquê** de cada decisão, consulte os [ADRs](adr/).

**Versão:** 1.0 · Maio de 2026

---

## Stack consolidada

| Camada | Tecnologia | Justificativa breve | ADR |
|---|---|---|---|
| Banco de dados | Oracle Database 23ai Free | Patrocínio + Vector Search nativo | [0001](adr/0001-banco-oracle-23ai.md) |
| Driver | python-oracledb (thin mode) | Mantido oficialmente pela Oracle, sem Instant Client | [0001](adr/0001-banco-oracle-23ai.md) |
| Backend + CRM interno | Django 5 + Python 3.12 | Django Admin já é o CRM; ecossistema rico em IA | [0002](adr/0002-django-em-vez-de-laravel.md) |
| Tema do Admin | django-unfold | Visual moderno baseado em Tailwind | [0002](adr/0002-django-em-vez-de-laravel.md) |
| Site público | Django Templates + Tailwind CSS | Sem build complexo, renderização server-side rápida | [0003](adr/0003-htmx-sem-vue.md) |
| Interatividade | HTMX + Alpine.js | Chat, calendário, formulários dinâmicos sem SPA | [0003](adr/0003-htmx-sem-vue.md) |
| Chatbot | Anthropic Python SDK + Tool Use | Streaming via SSE; tools garantem grounding | — |
| Embeddings | A definir na Sprint 0 | Decisão registrada em ADR-0004 ao fim da Sprint 0 | [0004](adr/0004-provedor-embeddings.md) |
| Tarefas async | Celery + Redis | E-mails, geração de slots, embeddings em batch | — |
| Containerização | Docker Compose | Dev local reproduzível + base do deploy | — |
| CI / CD | GitHub Actions | Lint, testes, build de imagem, deploy | — |
| Deploy | OCI Compute / Container Instances | Coerência com patrocínio Oracle | — |

---

## Modelo de dados

### Entidades principais

| Tabela | Função |
|---|---|
| `ESPECIALIDADE` | Catálogo de subespecialidades oftalmológicas (refrativa, catarata, retina, glaucoma, lentes de contato, pediátrica, plástica ocular) |
| `MEDICO` | Dados profissionais: CRM, RQE, especialidades, foto, contato |
| `MEDICO_ESPECIALIDADE` | Relação N:N médico ↔ especialidade |
| `PACIENTE` | Dados pessoais com CPF criptografado + hash determinístico para busca |
| `AGENDA_REGRA` | Regra recorrente semanal de disponibilidade por médico |
| `AGENDA_SLOT` | Slots gerados a partir das regras |
| `CONSULTA` | Agendamento de paciente em slot |
| `PRONTUARIO` | Agregador único por paciente |
| `EVOLUCAO` | Registro append-only com trigger de imutabilidade |
| `LEAD` | Contato iniciado no chat que ainda não virou consulta |
| `INTERACAO_CHAT` | Cada turno da conversa do chatbot |
| `FAQ_VECTOR` | FAQ da clínica com coluna `VECTOR` para busca semântica |
| `USUARIO` | Autenticação Django (perfis: medico, recepcao) |
| `LOG_ACESSO` | Auditoria LGPD de visualizações de prontuário |

### Diagrama relacional (alto nível)

```
ESPECIALIDADE ──< MEDICO_ESPECIALIDADE >── MEDICO ──┐
                                                     │
                                                     ↓
                                  AGENDA_REGRA → AGENDA_SLOT
                                                     │
                                                     ↓
                       PACIENTE ────────────────> CONSULTA
                         │                            │
                         ↓                            ↓
                    PRONTUARIO ──< EVOLUCAO >─────────┘
                         │
                         ↓
                    LOG_ACESSO

   Fluxo separado do CRM:

   INTERACAO_CHAT ──→ LEAD ──(converte)──→ CONSULTA

   Busca semântica:

   FAQ_VECTOR (com coluna VECTOR) ←─ consulta do chatbot
```

---

## Decisões não-negociáveis no banco

### Imutabilidade do prontuário

```sql
-- Trigger BEFORE UPDATE OR DELETE em EVOLUCAO
CREATE OR REPLACE TRIGGER trg_evolucao_imutavel
BEFORE UPDATE OR DELETE ON EVOLUCAO
FOR EACH ROW
BEGIN
    RAISE_APPLICATION_ERROR(
        -20001,
        'EVOLUCAO é append-only por exigência do CFM. Use nova evolução com referência à anterior.'
    );
END;
/
```

Justificativa: CFM exige prontuário não-alterável. Implementar no banco garante que mesmo um bug grave da aplicação ou um SQL injection não corrompa o registro.

### Anti-overbooking

```sql
ALTER TABLE AGENDA_SLOT
ADD CONSTRAINT uk_slot_medico_horario
UNIQUE (MEDICO_ID, DATA, HORA_INICIO);
```

Combinado com transação serializável no momento do agendamento, garante que duas requests simultâneas não criem consultas duplicadas no mesmo slot.

### CPF: criptografia + busca

- **Storage:** AES-256 (`DBMS_CRYPTO`) com chave gerenciada fora do banco
- **Busca:** HMAC-SHA256 com pepper externo, gerando hash determinístico
- **Nunca:** armazenar CPF em texto plano. Nunca usar SHA-256 puro (rainbow table trivial para 11 dígitos)

### Soft delete

Campos `ATIVO` (boolean) em `PACIENTE` e `MEDICO`. Nunca executar `DELETE` físico — viola exigência do CFM de retenção de 20 anos.

### Vector Search

```sql
CREATE TABLE FAQ_VECTOR (
    ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    PERGUNTA VARCHAR2(500) NOT NULL,
    RESPOSTA CLOB NOT NULL,
    EMBEDDING VECTOR(384, FLOAT32),   -- 384 = all-MiniLM (ADR-0004). Mudar a dimensão
                                      -- exige migration + re-embedding de tudo.
    CRIADO_EM TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índice HNSW para busca rápida
CREATE VECTOR INDEX idx_faq_embedding
ON FAQ_VECTOR (EMBEDDING)
ORGANIZATION INMEMORY NEIGHBOR GRAPH
DISTANCE COSINE
WITH TARGET ACCURACY 95;
```

Busca via:
```sql
SELECT PERGUNTA, RESPOSTA
FROM FAQ_VECTOR
ORDER BY VECTOR_DISTANCE(EMBEDDING, :query_embedding, COSINE)
FETCH FIRST 3 ROWS ONLY;
```

---

## Padrões de código

### Estrutura de apps Django

```
clinicos/
├── apps/
│   ├── core/          # User custom, base models, helpers transversais
│   ├── agenda/        # AgendaRegra, AgendaSlot, geração
│   ├── crm/           # Paciente, Medico, Lead, funil
│   ├── prontuario/    # Prontuario, Evolucao, log de acesso
│   ├── chatbot/       # ChatService, Tools, INTERACAO_CHAT
│   └── site_publico/  # Views do site institucional
├── config/
│   ├── settings/      # base.py, dev.py, prod.py
│   ├── urls.py
│   └── celery.py
├── templates/         # Templates Django globais
├── static/            # Assets compilados
└── manage.py
```

### Service layer

Toda lógica de negócio em `services/` dentro de cada app. Views ficam finas:

```python
# apps/agenda/views.py
def agendar_consulta(request, slot_id):
    consulta = AgendamentoService.agendar(
        slot_id=slot_id,
        paciente_data=request.POST,
    )
    return render(request, "agenda/confirmacao.html", {"consulta": consulta})

# apps/agenda/services/agendamento.py
class AgendamentoService:
    @staticmethod
    @transaction.atomic
    def agendar(slot_id, paciente_data):
        # toda lógica aqui
```

### Repositórios para queries complexas

Quando uma query envolve múltiplas tabelas ou SQL bruto (Vector Search, por exemplo), encapsular em repositório:

```python
# apps/chatbot/repositories/faq.py
class FAQRepository:
    @staticmethod
    def buscar_semantica(embedding: list[float], top_k: int = 3):
        with connection.cursor() as cur:
            cur.execute(...)  # raw SQL com VECTOR_DISTANCE
            return cur.fetchall()
```

### Tools do chatbot

Cada tool é uma classe com schema, execução e validação:

```python
# apps/chatbot/tools/buscar_slots.py
class BuscarSlotsTool(BaseTool):
    name = "buscar_slots"
    description = "Busca horários disponíveis para uma especialidade..."
    input_schema = {...}

    def execute(self, especialidade: str, periodo: str) -> dict:
        # consulta o banco, retorna slots reais
```

---

## Conformidade legal

| Requisito | Implementação |
|---|---|
| LGPD — base legal | Tutela da saúde (Art. 11, II, "f") |
| LGPD — auditoria | Tabela `LOG_ACESSO` populada por middleware |
| LGPD — dado sensível | CPF e diagnósticos com criptografia em coluna |
| LGPD — consentimento | Banner no site + registro timestampado |
| LGPD — direito de acesso | Endpoint autenticado para paciente solicitar seus dados (MVP2) |
| CFM — retenção | 20 anos mínimo, sem DELETE físico |
| CFM — imutabilidade | Trigger no Oracle, não só validação na aplicação |
| CFM — autoria | Hash da evolução + ID do médico + timestamp |

---

## Ambientes

| Ambiente | Propósito | Banco | Domínio |
|---|---|---|---|
| `dev` | Desenvolvimento local | Oracle 23ai Free em Docker | localhost |
| `staging` | Demonstrações e revisões com cliente | Oracle 23ai em OCI (tier free) | staging.clinicos.com.br |
| `prod` | Produção | Oracle 23ai em OCI | clinicos.com.br |

---

## Performance e observabilidade

- **Logs estruturados** (JSON) com `python-json-logger`
- **Sentry** para captura de exceções
- **Uptime monitoring** com UptimeRobot ou equivalente
- **Métricas custom:** custo de chamadas Claude API por turno, tempo médio de resposta da tool, taxa de fallback do chatbot
- **EXPLAIN PLAN** revisado nas queries críticas na Sprint 6

---

## Segurança

- HTTPS obrigatório em todos os ambientes
- Headers de segurança: HSTS, X-Frame-Options, Content-Security-Policy
- Rate limiting por IP no site público (django-ratelimit)
- Honeypot anti-spam no formulário inicial do chat
- Validação rigorosa de input antes de qualquer chamada à LLM
- Secrets em variáveis de ambiente, nunca em código
- Backup diário do Oracle com teste mensal de restore

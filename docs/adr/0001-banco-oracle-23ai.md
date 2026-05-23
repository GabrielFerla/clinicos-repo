# ADR-0001: Banco de dados — Oracle Database 23ai

- **Status:** ✅ Accepted
- **Data:** 2026-05-17
- **Decisor(es):** Dev lead + patrocinador acadêmico

## Contexto

O ClinicOS precisa de um banco de dados relacional para:

- Armazenar dados clínicos sensíveis (CPF, prontuário)
- Garantir imutabilidade de registros legais (CFM exige)
- Suportar busca semântica para o FAQ do chatbot (RAG)
- Lidar com concorrência em agendamentos (anti-overbooking)

Além do requisito técnico, há um requisito institucional: **o projeto tem patrocínio da Oracle como TCC**. Isso constrange a escolha mas também abre oportunidades.

## Alternativas consideradas

### Opção A: PostgreSQL + pgvector
- **Prós:**
  - Comunidade enorme, drivers maduros em todas as linguagens
  - Sem fricção de licença ou client externo
  - `pgvector` resolve a parte vetorial muito bem
  - Curva de aprendizado menor
- **Contras:**
  - **Inviabiliza o patrocínio acadêmico** (deal-breaker)
  - Sem narrativa diferenciada na banca

### Opção B: Oracle 23ai
- **Prós:**
  - **Atende ao patrocínio**
  - AI Vector Search nativo (sem extensão externa)
  - JSON Relational Duality (uma tabela é relacional e documento)
  - Maturidade comprovada em ambientes regulados (saúde, finanças)
  - Features de segurança nativas (Transparent Data Encryption, etc.)
- **Contras:**
  - Driver Python (`python-oracledb`) tem menos mindshare que `psycopg`
  - Imagem Docker pesada (~5GB)
  - Vendor lock-in se o projeto for comercial no futuro
  - Curva mais íngreme para devs sem background Oracle

### Opção C: Oracle 19c
- **Prós:**
  - Versão mais conhecida e estável
  - Mais material e exemplos disponíveis
- **Contras:**
  - Sem Vector Search nativo (perde o diferencial mais forte)
  - Versão sem features modernas, menos vendável academicamente

## Decisão

**Adotar Oracle Database 23ai Free.**

Driver: `python-oracledb` em **thin mode** (sem necessidade de Oracle Instant Client em produção, simplifica deploy e Dockerfile).

## Consequências

### Positivas
- Patrocínio acadêmico mantido
- Vector Search nativo elimina necessidade de banco vetorial separado (Qdrant, Pinecone)
- Narrativa técnica forte para a banca: "usamos features da edição 2024 do Oracle"
- Possibilidade de explorar JSON Duality em iteração futura sem mudar de banco
- Conformidade legal facilitada (auditoria, criptografia, retenção)

### Negativas
- Menos exemplos públicos de Django + Oracle 23ai (vamos contribuir com isso)
- Risco técnico de fricção do driver em features muito novas — **mitigado pela Sprint 0**
- Imagem Docker grande impacta tempo de CI

### Neutras / mitigações
- Sprint 0 dedicada a validar o stack ponta a ponta antes de qualquer trabalho de produto
- ADR-0004 trata especificamente da decisão sobre embeddings, dependente do que validarmos na Sprint 0
- Deploy em OCI (oferecido pela Oracle) elimina custo do banco em produção via tier free

## Notas adicionais

- Documentação Vector Search 23ai: https://docs.oracle.com/en/database/oracle/oracle-database/23/vecse/
- python-oracledb thin mode: https://python-oracledb.readthedocs.io/en/latest/user_guide/initialization.html
- Decisão de provedor de embeddings (qual modelo gera os vetores) é separada e está em ADR-0004

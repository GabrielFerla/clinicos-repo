# ADR-0004: Provedor de embeddings

- **Status:** 🟡 Proposed (decisão sai ao final da Sprint 0)
- **Data:** 2026-05-17
- **Decisor(es):** Dev lead, após validação técnica na Sprint 0

## Contexto

O ClinicOS usa **Vector Search nativo do Oracle 23ai** para a busca semântica do FAQ do chatbot (ADR-0001). O Oracle armazena os vetores, mas **não gera embeddings por padrão** — eles precisam vir de algum modelo, que pode estar:

- **Externo** (API OpenAI, Voyage AI, Cohere) — gera vetor → grava no Oracle
- **Interno ao Oracle** via modelo ONNX (`DBMS_VECTOR.UTL_EMBEDDING_MODELS`)
- **Local** via SentenceTransformers em Python no próprio Django

A escolha tem impacto em custo, latência, dependências externas e narrativa acadêmica.

## Alternativas consideradas

### Opção A: OpenAI `text-embedding-3-small`
- **Prós:**
  - Mais utilizado da indústria, fácil de obter ajuda
  - Boa relação custo/qualidade (~$0.02 / 1M tokens)
  - Dimensões: 1536 (ou redutíveis)
  - SDK Python maduro
- **Contras:**
  - Dependência adicional (outra API)
  - Dados saem para a OpenAI (revisar LGPD para FAQ pública não é problema; para dados de paciente seria)
  - Custo recorrente (pequeno mas existe)

### Opção B: Voyage AI `voyage-3` ou `voyage-3-large`
- **Prós:**
  - Performance excelente em benchmarks
  - Empresa especializada em embeddings
  - Anthropic recomenda Voyage como parceiro
  - Free tier generoso para começar
- **Contras:**
  - Menos ubíquo que OpenAI
  - Dependência externa adicional

### Opção C: ONNX dentro do Oracle 23ai
- **Prós:**
  - **Tudo dentro do banco** — narrativa máxima para banca e patrocinador
  - Sem dependência externa, sem custo recorrente
  - Latência mínima (mesmo processo)
  - Reforça a tese "Oracle como plataforma de IA"
- **Contras:**
  - Documentação ainda em maturação
  - Modelos disponíveis são limitados (geralmente all-MiniLM-L6-v2 e similares)
  - Qualidade dos vetores tipicamente inferior aos modelos comerciais
  - Setup mais complexo
  - **Risco técnico mais alto** — pode não funcionar e exigir fallback

### Opção D: SentenceTransformers local em Python
- **Prós:**
  - Gratuito e offline
  - Vários modelos disponíveis
- **Contras:**
  - Adiciona peso ao container Django (~500MB para o modelo)
  - CPU-bound se rodar inferência local (lento em servidores básicos)
  - Não aproveita o ecossistema Oracle

## Decisão

**Decisão pendente até o fim da Sprint 0**, com a seguinte ordem de preferência:

1. **Primeira tentativa: ONNX no Oracle 23ai** — pelo valor narrativo e simplicidade arquitetural
2. **Se ONNX não funcionar ou qualidade for ruim: Voyage AI** — pela parceria com Anthropic e qualidade
3. **Fallback final: OpenAI** — caminho seguro e conhecido

A decisão será materializada como **atualização deste ADR** ao final da Sprint 0, com o teste empírico que justifique a escolha.

## Consequências (a serem detalhadas após decisão)

_(esta seção será preenchida quando a decisão for tomada)_

## Critérios de avaliação na Sprint 0

Para tomar a decisão, na Sprint 0 vamos:

1. Configurar cada opção em ambiente isolado
2. Gerar embeddings para 10 perguntas/respostas do FAQ-piloto
3. Executar busca semântica com 5 queries representativas
4. Comparar:
   - Qualidade do resultado (manual, 1-5)
   - Latência de geração de embedding (ms)
   - Latência de busca via Vector Search (ms)
   - Custo estimado para 1000 queries/mês
   - Complexidade de setup e manutenção

Resultado registrado em `docs/sprint-0/embeddings-comparison.md`.

## Notas adicionais

- Independente da escolha, a **dimensão do vetor** será fixa em toda a coluna `FAQ_VECTOR.EMBEDDING` — mudar dimensão depois exige migration e re-embedding completo.
- Para o MVP1, apenas a FAQ é vetorizada. Em MVP2 pode-se considerar vetorizar prontuários (pacientes similares, queixas recorrentes), o que **aumenta a importância de uma escolha boa agora**.

# ADR-0004: Provedor de embeddings

- **Status:** 🟡 Partially decided — preliminar para spike; decisão final na Sprint 5
- **Data:** 2026-05-23
- **Decisor(es):** Dev lead, após Checkpoint 3 da Sprint 0

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
  - Dimensões: 1536 (ou redutíveis via parâmetro `dimensions`)
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
  - Dimensão padrão de 1024 (alinhado com a coluna originalmente planejada na sprint)
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
  - Zero dependência externa e zero API key — narrativa de "sem custo" preservada
- **Contras:**
  - Adiciona peso ao container Django (~120MB para `all-MiniLM-L12-v2`)
  - CPU-bound se rodar inferência local (lento em servidores básicos)
  - Não aproveita o ecossistema Oracle

## Decisão

**Decisão preliminar (válida para o spike e para iniciar a Sprint 1):**

> Adotar **SentenceTransformers `all-MiniLM-L12-v2`** (Opção D) como provedor de embeddings para o spike e como baseline para começar a Sprint 1. Dimensão fixada em **384**.

**Por que esta — e não a primeira preferência (ONNX)?**

1. **ONNX-in-Oracle (Opção C, primeira escolha do ADR original):** tentado primeiro, dentro do timebox de 90 min do Checkpoint 3. A URL OCI pré-assinada distribuída pela Oracle para o modelo padrão (`all_MiniLM_L12_v2.onnx`) retornou **HTTP 401 (expirada)**. Re-empacotar o modelo via HuggingFace + `optimum` para uploadar no Oracle ficaria fora do budget do spike. Caminho **não foi eliminado, apenas adiado** — vale tentar de novo na Sprint 5.
2. **Voyage AI (Opção B) e OpenAI (Opção A):** ambos exigiriam criação de conta + chave de API. O usuário **não autorizou contratar/cadastrar nenhum provedor pago no spike**. Sem chave, sem teste.
3. **SentenceTransformers (Opção D):** roda offline, sem chave, sem custo. Preserva a narrativa de "zero custo, zero key" para a banca. Bate o critério funcional do spike: query `"Quanto custa?"` retornou no top-1 `"Quanto custa uma consulta particular?"` (dist 0.38) e no top-3 também `"Vocês aceitam convênio?"` — caso explicitamente esperado na sprint.

**Decisão final (a tomar na Sprint 5):** ainda em aberto. O spike provou que a stack funciona com 384 dim + SentenceTransformers, mas isso é o suficiente para destravar a Sprint 1 (CRM, agenda, site), **não** para fechar a escolha do chatbot real. A Sprint 5 (chatbot) deve re-avaliar:

- **ONNX-in-Oracle** com modelo empacotado via `optimum` (origem HuggingFace) — primeira preferência ainda
- **Voyage `voyage-3`** (1024 dim, parceria Anthropic) — com chave de API real
- **OpenAI `text-embedding-3-small`** com `dimensions=1024` — com chave de API real

## Consequências

### Decorrentes da escolha preliminar
- Tabela `FAQ_SPIKE` foi criada no schema `CLINICOS` com `EMBEDDING VECTOR(384, FLOAT32)`. **Se o provedor final tiver dimensão diferente** (1024 do Voyage/OpenAI, ou 768 de outros MiniLM), será necessário **migration + re-embedding completo** de todas as linhas vetorizadas. Não é destrutivo, mas é trabalho.
- A coluna foi reduzida de 1024 (planejado na sprint) para **384** porque o modelo `all-MiniLM-L12-v2` produz vetores nessa dimensão. Documentar isso na Sprint 1 ao criar o schema definitivo.
- Imagem container Django passa a embarcar SentenceTransformers + modelo (~120MB). Em produção, considerar pre-pull do modelo no build (não no first-run) para evitar cold start de 10–20s.

### Decorrentes da operação do Oracle 23ai
- A imagem `gvenzl/oracle-free:23-slim` sobe com `vector_memory_size=0` por padrão, o que **trava a criação de índices HNSW**. No spike foi necessário `ALTER SYSTEM SET vector_memory_size = 512M SCOPE=SPFILE` + bounce da instância. A mudança ficou persistida no SPFILE do volume Docker, mas **o `docker-compose.yml` da Sprint 1 precisa explicitar este parâmetro** (via init script ou variável de ambiente) para que o setup seja reproduzível em outras máquinas. Sugestão: `512M` para MVP1 (só FAQ vetorizada), **`1G` se o MVP2 vetorizar prontuários** também.
- **Schema obrigatório para vetores: `CLINICOS`** (default tablespace `USERS`). O schema `SYSTEM` **não suporta** coluna `VECTOR` (retorna `ORA-43853`). Produção segue o mesmo padrão — vetores nunca em `SYSTEM`.

### Baseline de performance (referência de regressão para a Sprint 5)
Medições do Checkpoint 3, 100 execuções, 1000 linhas sintéticas, dimensão 384, distância COSINE, top-3:

| Cenário        | Latência média | p95     |
|----------------|----------------|---------|
| Sem índice     | 0.47 ms        | 0.61 ms |
| Índice IVF     | 0.48 ms        | —       |
| Índice **HNSW**| **0.22 ms**    | **0.36 ms** |

HNSW reduziu a latência média em ~53% e o p95 em ~41% comparado ao full scan. IVF foi indistinguível do full scan neste volume — HNSW é a escolha padrão.

Usar **0.22 ms p50 / 0.36 ms p95** como linha de base de regressão quando a Sprint 5 trocar de provedor: se a nova dimensão (ex.: 1024) degradar mais do que ~2x este número em volume comparável, vale reconsiderar.

## Critérios de avaliação na Sprint 0

Para tomar a decisão, na Sprint 0 vamos:

1. ✅ Configurar cada opção em ambiente isolado — **parcial:** SentenceTransformers configurado; ONNX-in-Oracle tentado e bloqueado por URL 401; Voyage/OpenAI pulados (sem chave, sem autorização do usuário)
2. ✅ Gerar embeddings para 10 perguntas/respostas do FAQ-piloto — **feito com SentenceTransformers `all-MiniLM-L12-v2`**
3. ✅ Executar busca semântica com 5 queries representativas — **feito; query `"Quanto custa?"` validada**
4. Comparar:
   - ✅ Qualidade do resultado (manual, 1-5) — **feito qualitativamente para SentenceTransformers; comparação cross-provider pulada**
   - ⚠️ Latência de geração de embedding (ms) — **medido apenas para SentenceTransformers**
   - ✅ Latência de busca via Vector Search (ms) — **feito, ver tabela acima**
   - ⏭️ Custo estimado para 1000 queries/mês — **pulado** (provedores pagos não testados)
   - ✅ Complexidade de setup e manutenção — **anotada para cada opção testada**

📌 **TODO Sprint 5:** materializar `docs/sprint-0/embeddings-comparison.md` com a tabela completa (cross-provider) quando os provedores faltantes forem testados.

## Pendências para Sprint 5

- [ ] Retentar **ONNX-in-Oracle** com modelo empacotado via `optimum` (origem HuggingFace) — não depender da URL OCI pré-assinada que expirou
- [ ] Avaliar **Voyage `voyage-3`** (1024 dim) com chave de API real
- [ ] Avaliar **OpenAI `text-embedding-3-small`** com `dimensions=1024` e chave de API real
- [ ] Materializar `docs/sprint-0/embeddings-comparison.md` com a comparação completa cross-provider (qualidade, latência geração, latência busca, custo/1000 queries, complexidade)
- [ ] Decidir o provedor **definitivo** do chatbot e atualizar este ADR para `🟢 Decided`
- [ ] Se a dimensão final for diferente de 384, planejar migration + re-embedding da `FAQ` (tabela definitiva da Sprint 5)

## Notas adicionais

- Independente da escolha, a **dimensão do vetor** será fixa em toda a coluna `FAQ.EMBEDDING` — mudar dimensão depois exige migration e re-embedding completo. Hoje está em 384 (spike); pode mudar na Sprint 5.
- Para o MVP1, apenas a FAQ é vetorizada. Em MVP2 pode-se considerar vetorizar prontuários (pacientes similares, queixas recorrentes), o que **aumenta a importância de uma escolha boa na Sprint 5** e o limite de `vector_memory_size` para `1G+`.
- A decisão preliminar **não** trava a Sprint 1 — o CRM/agenda/site não usam embeddings. Só a Sprint 5 (chatbot) depende desta escolha.

# Chat MVP — guia de implementação

> Documento vivo, escrito para quem vai implementar. Descreve a **fatia vertical mínima do chatbot**: o que construir, em que ordem, e as armadilhas medidas neste ambiente. Para o estado geral do código, ver [`STATUS.md`](STATUS.md); para a arquitetura completa, [`ARQUITETURA.md`](ARQUITETURA.md); para as tarefas, [`../sprints/`](../sprints/).
>
> **Escopo desta entrega:** chat com RAG e tools de **leitura**. Não agenda consulta.

---

## 1. Objetivo

O fluxo central de valor do ClinicOS é *"paciente conversa com chatbot no site e agenda consulta"*. Hoje esse fluxo não existe em nenhuma linha de código do produto.

Esta entrega faz a primeira metade funcionar de ponta a ponta: **abrir uma página, perguntar, e receber resposta com dados vindos do Oracle** — não inventados pelo modelo.

Ao fim, isto tem que funcionar:

| Pergunta | Caminho técnico |
|---|---|
| "Quais especialidades vocês atendem?" | tool `listar_especialidades_disponiveis` → ORM |
| "Tem horário com oftalmologista?" | tool `buscar_slots` → ORM |
| "A clínica atende convênio?" | tool `buscar_faq` → `VECTOR_DISTANCE` no Oracle 23ai |

Tudo local, com Ollama, sem chave de API.

**Decisões travadas:** tools apenas de leitura · somente Ollama · Oracle 23ai real (Vector Search é o diferencial acadêmico) · modelar apenas o subset que o chat precisa.

---

## 2. Ponto de partida

**No `clinicos-repo`:** 7 apps Django criados, **todos stubs** (os `models.py` têm 3 linhas). **Zero models e zero migrations em todo o histórico git.** `config/urls.py` é `urlpatterns = []` — nenhuma rota, nem `/admin/`. O único código de domínio é `apps/core/security/` (cripto de CPF), com 87 testes.

**No `clinicos-spike`:** Vector Search, Tool Use e streaming SSE foram validados — mas em **três checkpoints isolados que nunca foram ligados entre si**. O `checkpoint-6` (chat) manda `[{"role":"user"}]` puro, sem system prompt, sem histórico e sem retrieval; o `checkpoint-4` (tool use) faz grounding por SQL de keyword, não vetorial. Nenhuma chamada Anthropic real aconteceu e o repo não tem um único teste.

O trabalho aqui é, portanto, **integrar peças já provadas** — não escrever do zero.

---

## 3. O que reaproveitar do spike

### Portar quase literal — 4 primitivas validadas

| Origem no spike | Destino |
|---|---|
| DDL `VECTOR(384, FLOAT32)` e índice HNSW com fallback IVF — `checkpoint-3-vector/scripts/01_create_table.sql`, `04_create_index.sql` | migrations `0002`/`0003` do `chatbot` |
| Query `VECTOR_DISTANCE(..., COSINE)` + bind `array.array("f")` — `checkpoint-3-vector/scripts/03_search.py` | `apps/chatbot/repositories/faq.py` |
| Loop de tool dispatch: `assistant(tool_calls)` → `role:tool(tool_call_id)` → 2ª chamada — `checkpoint-4-claude/scripts/03_tool_use_demo.py:130-215` | `apps/chatbot/services/chat.py` |
| Gerador SSE + headers (`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`) e a fiação HTMX (`sse-swap`, `sse-close`, `htmx.process`) — `checkpoint-6-htmx/spike/chat/` | `apps/chatbot/views.py` + template |

### Reaproveitar como conteúdo

O `SYSTEM_PROMPT` do `checkpoint-4` (persona + "NUNCA invente horários"), as FAQs de `checkpoint-3-vector/faqs.json` como seed, o `04_adversarial.py` como base dos testes de grounding, e os gotchas de Oracle documentados nos READMEs — que valem mais que o código.

### Não reaproveitar, com motivo

- **`checkpoint-6/views.py` tem 3 bugs** que não podem ir para produção: descarta `delta.reasoning` (causa tela em branco — ver §4.2), não escapa HTML (XSS via prompt injection, porque htmx injeta o payload como HTML) e manda `str(exc)` para o browser (vaza DSN, usuário do Oracle e caminhos de arquivo).
- **Schema:** o spike roda no usuário `system` com tabelas `_SPIKE` — e `VECTOR` nem funciona em `SYSTEM` (`ORA-43853`). Produção usa o usuário `clinicos`.
- **Sem ORM:** tudo é `oracledb` cru, sem models nem migrations.
- **Ingestão não-idempotente:** `DELETE` + insert a cada rodada.
- **Settings e testes:** arquivo único com `DEBUG=True` e senhas triviais; zero testes.

---

## 4. Achados de ambiente (medidos, não presumidos)

Cinco medições feitas neste host antes de planejar. Todas mudam alguma decisão.

### 4.1 O Ollama não é alcançável pelo container — bloqueador duro

`ss -ltnp` mostra `LISTEN 127.0.0.1:11434`. O container **não alcança**, e `extra_hosts` sozinho não resolve. Precisa de `OLLAMA_HOST=0.0.0.0` no serviço do host **e** `extra_hosts` no compose. Sem isso: `APIConnectionError` em tudo.

### 4.2 O modelo instalado não serve

O spike usou `qwen3:8b`, que **não está mais instalado**. Só há `qwen3:4b`, um modelo *thinking*. Tempo até o primeiro token **visível**:

| Configuração | Chars de raciocínio | 1º token visível | Veredito |
|---|---:|---:|---|
| `/v1` padrão | 9175 | **32,5s** | tela em branco |
| `"think": false` no `/v1` | 3570 | 13,4s | **ignorado** |
| `chat_template_kwargs.enable_thinking=false` | 5984 | 26,3s | **ignorado** |
| `/no_think` no system prompt | 10822 | 45,5s | **ignorado** |
| `reasoning_effort: "none"` | 0 | 0,6s | **CoT em inglês vaza como resposta** |
| `/api/chat` nativo `"think": false` | 0 | 1,8s | **CoT vaza como resposta** |

A causa raiz está no template do modelo (`ollama show --template qwen3:4b`), que termina com um prefill **incondicional** de `<think>`. `think:false` só faz o Ollama parar de *parsear* — não impede o modelo de raciocinar. **Você escolhe entre esperar o raciocínio ou mostrá-lo ao paciente.**

Fluxo completo medido (tool + resposta): **9,4s de tela em branco** no caso bom; a decisão de tool variou de 3,2s a 24,6s entre queries. Intervalo real: **8s a 45s**. A meta de [`METRICAS.md`](METRICAS.md) é TTFT ≤ 2s.

**O bom:** tool use com o 4b é confiável — **6/6** nas queries reais, incluindo normalizar "oftalmologista" → `{"especialidade": "Oftalmologia"}` e inferir `periodo_preferido: "manha"`. E acertou não chamar tool nenhuma no "Bom dia!". **Tool use não é o risco; latência é.**

**Ação:** usar variante sem thinking — `qwen3:4b-instruct-2507`, `qwen2.5:3b-instruct`, ou um Modelfile com `<think></think>` já preenchido. Validar pelo tempo até o primeiro `delta.content` **não-vazio** — não pelo primeiro byte, que mede raciocínio e engana.

### 4.3 Existe GPU, e ela está quase cheia

RTX 3060 Laptop, 6144 MiB, com **529 MiB livres** (o desktop Windows consome ~2,3 GB). O `qwen3:4b` roda **100% em GPU** ocupando 3,2 GB de VRAM — por isso o processo no host usa só ~830 MB de RAM.

**Não puxar o `qwen3:8b`** (~5,2 GB de pesos): faria offload para CPU e reproduziria os 9-13s de TTFT do spike — que provavelmente *foi* isso, não uma propriedade do modelo. O gargalo de memória aqui é **VRAM, não RAM**.

RAM com a stack de pé: Oracle ~2,0-2,5 GB (a Free Edition é **limitada a 2 GB por licença**, e o `vector_memory_size=512M` sai de dentro desse teto) + Django ~0,3 GB + Redis/Mailhog ~0,05 GB ≈ **3,2 GB**, contra 5,0 GB livres. Cabe, parando a stack `medreview`.

### 4.4 O Ollama serializa requests

`llama-server` roda com `-np 1`. Dois requests paralelos: o segundo só começa quando o primeiro termina. E **cada turno consome o slot duas vezes** (decisão de tool + resposta). Duas abas = fila. Com 529 MiB de VRAM livres, `OLLAMA_NUM_PARALLEL=2` não cabe. Assumir **uma conversa por vez** em dev.

### 4.5 Não há Python utilizável no host

Só Python 3.10 sem venv; Django e pytest não estão instalados. `make test` (`pytest -q`) falha com *command not found*. **Todo comando roda via `docker compose exec django ...`.**

---

## 5. Blocos de execução

Caminho crítico: **0C → 1A → 1B → 3C → 4A → 5A**. O resto é folga.

### Bloco 0 — Desbloqueio

**0A · Fundação de testes** — `pyproject.toml`, `conftest.py` (novo, raiz), `ci.yml`, `Makefile`

- Registrar markers `oracle` e `llm`. Hoje `--strict-markers` sem seção `markers` faz o primeiro `@pytest.mark.oracle` virar **erro de coleta** — zero testes rodam, não é skip.
- `conftest.py` com `os.environ.setdefault` **no nível de módulo** — conftests da raiz carregam antes do `pytest_configure` do pytest-django, que é onde `django.setup()` dispara o `env("DJANGO_SECRET_KEY")` sem default de [`base.py:67`](../config/settings/base.py). Mais `pytest_collection_modifyitems` com auto-skip dos markers, que é melhor que `-m "not oracle"` só no CI porque protege quem roda `pytest` na mão.
- Corrigir os alvos do Makefile para rodarem via `docker compose exec`.

**0B · Infra e conectividade** — `docker-compose.yml`, `config/`, `settings/base.py`, `requirements/base.txt`, `.env.example`

- **`OLLAMA_HOST=0.0.0.0`** no serviço Ollama do host + `extra_hosts: ["host.docker.internal:host-gateway"]` no compose. Validar de dentro do container **antes de escrever qualquer código**:
  ```
  docker compose exec django python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags',timeout=5).status)"
  ```
- `config/celery.py` + `config/__init__.py`: o chat não usa fila, mas o serviço `celery-worker` está em **crash-loop** hoje, queimando recursos durante toda a implementação.
- `wsgi.py`/`asgi.py`: o `setdefault` aponta para `config.settings` (pacote vazio) → trocar para `config.settings.dev`.
- **Uma única dependência nova:** `openai>=1.50,<2.0`.
- Settings novos: `LLM_*`, `EMBEDDING_*` (dim 384), `CHAT_STREAM_MAX_SEGUNDOS`, `CHAT_HISTORICO_MAX_TURNOS`. Sempre via `env(...)` com default, nunca `os.environ`.
- **Novo `infra/oracle-init/02_grants.sql`**: `ALTER USER clinicos QUOTA UNLIMITED ON USERS;` + `GRANT CREATE MINING MODEL TO clinicos;`. Hoje não existe e o `CREATE VECTOR INDEX` falha. Atenção: init scripts só rodam em **volume novo** — num volume existente, aplicar na mão via sqlplus.

**0C · `Usuario` + admin** `[S1-8 parcial]` — **bloqueia o Bloco 1**

- `Usuario(AbstractUser)` com `perfil` (TextChoices), `db_table="USUARIO"`. `AbstractUser` e não `AbstractBaseUser` porque o Admin já funciona e a S2-3 pede exatamente isso.
- `config/urls.py`: `admin.site.urls` → resolve os débitos #1 e #3 do STATUS de uma vez.

Débitos #4 (`--cov-fail-under`) e #5 (bandit) ficam fora: ligar o gate de cobertura agora reprova o PR por causa de código recém-nascido.

### Bloco 1 — Dados `[S1-8 parcial][S1-9][S1-11][S1-12]`

**1A · Models** — um único agente: `makemigrations` é global e agentes concorrentes gerariam grafos conflitantes.

| Model | App | Notas |
|---|---|---|
| `Especialidade` | crm | `descricao` como **CharField** (TextField vira NCLOB, proibido em `WHERE`/`ORDER BY`) |
| `Medico` + `MedicoEspecialidade` | crm | unique `(crm_numero, crm_uf)` |
| `AgendaSlot` | agenda | unique `(medico, data, hora_inicio)` `[S1-11]` |
| `FaqVector` | chatbot | + `embedding_modelo` e `embedding_dim` — ver invariante em 2 |
| `InteracaoChat` | chatbot | tokens, `latencia_ms`, `tools_usadas`, `faq_ids`, `alucinacao_detectada` `[S5-26]` |

**Fora agora:** Paciente (traz a decisão do CPF cifrado, merece PR próprio), Consulta, Lead, Prontuario, Evolucao, LogAcesso, AgendaRegra.

Gotchas: verificar o uppercase **de fato** com `sqlmigrate crm 0001` logo após a primeira migration; **nomear explicitamente** todo índice e constraint (limite de 30 chars — nome autogerado é truncado de forma não determinística e quebra o rollback).

**1B · Coluna VECTOR e índice** `[S1-9][S1-12]`

O ORM não conhece `VECTOR`. O model declara só os campos escalares; a coluna entra por migration separada, com **`RunPython` guardado por vendor** — nunca `RunSQL` puro, que rodaria no SQLite do CI e explodiria:

```python
def _add_vector_column(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.execute("ALTER TABLE FAQ_VECTOR ADD (EMBEDDING VECTOR(384, FLOAT32))")
```

Assim o CI cria `FAQ_VECTOR` sem `EMBEDDING` e todo teste de model/admin/tool roda normalmente. A coluna precisa ser **nullable** (o `create()` acontece antes do embedding existir). Dimensão **384 como literal** — migration não pode ler `settings`, senão o estado do schema vira função do ambiente.

Custom `VectorField` foi descartado: o único uso do vetor é `VECTOR_DISTANCE` no `ORDER BY`, que não tem expressão ORM — a query continua SQL cru de qualquer forma.

Índice com **fallback em cascata**: HNSW (`ORGANIZATION INMEMORY NEIGHBOR GRAPH DISTANCE COSINE`) → se `ORA-51962`, IVF (`NEIGHBOR PARTITIONS`) → se falhar, WARNING e segue. **O índice é performance, nunca correção** (0,47ms sem índice em 1k linhas, medido no spike). Isso o tira do caminho crítico da demo.

**Conflito a resolver:** [`ARQUITETURA.md`](ARQUITETURA.md) diz `VECTOR(1024)`, o [ADR-0004](adr/0004-provedor-embeddings.md) diz **384**. Fixar 384 e corrigir o ARQUITETURA no mesmo PR — deixar os dois vivos garante que alguém crie a coluna errada e só descubra no `ORA-51803`.

**1C · Seeder** `[S1-16 parcial]` — nome do command: **`seed_initial`**, porque `infra/scripts/setup.sh:98` já procura por ele; assim `make setup` passa a rodá-lo sozinho.

### Bloco 2 — Núcleo de IA (paralelo ao Bloco 1)

Não importa models → roda em paralelo e é testável em CI sem rede.

- `apps/chatbot/services/llm/` — Protocol `LLMClient`, impl Ollama, **impl Fake** (scriptável), factory. Isola o provider para pagar a dívida da Anthropic depois sem tocar no `ChatService`.
- `apps/chatbot/services/embeddings.py` — provider + fake determinístico (384 floats derivados de `sha256`).
- `apps/chatbot/prompts.py` `[S5-7]`.

**Embeddings via Ollama (`all-minilm`, 46 MB, 384 dim), não sentence-transformers.** Remove `torch` da imagem Django: **−2,3 GB de imagem**, build de ~10min para ~2min, **−600MB a −1GB de RSS**. A dimensão é a mesma família do ADR-0004, então `VECTOR(384)` continua e não há re-embedding: muda o *runtime* que serve o modelo, não o modelo decidido. Latência de embed ~20-50ms via HTTP local contra ~10ms in-process — irrelevante frente aos segundos do LLM.

> **Invariante crítica:** indexar com um modelo e consultar com outro devolve **lixo sem erro nenhum**. Guardar `embedding_modelo` e `embedding_dim` na linha, e fazer o `buscar_faq` **recusar** quando divergir.

### Bloco 3 — Tools e repositório

`BaseTool` (`name`, `description`, `input_schema`, `execute() -> dict`) + `ToolRegistry`, conforme [`ARQUITETURA.md`](ARQUITETURA.md). Três tools de leitura: `listar_especialidades_disponiveis` `[S5-9]`, `buscar_slots` `[S5-10]`, `buscar_faq` `[S5-13]`.

Para `buscar_slots`, **gerar o `enum` do `input_schema` a partir do banco**: com modelo pequeno, restringir o vocabulário é a defesa mais eficaz contra parâmetro inventado.

#### `repositories/faq.py` — o ponto técnico mais delicado

O `OracleParam` do Django faz `force_str()` em tipos que não conhece: um `array.array("f", [...])` passado pelo `connection.cursor()` vira **literalmente a string `"array('f', [0.1, ...])"`**. Não dá erro de sintaxe — dá `ORA-` confuso ou, pior, ranking errado. Usar o **cursor cru do driver**:

```python
raw = connection.connection.cursor()   # oracledb puro, sem OracleParam
```

Provar em 30 segundos antes de escrever a camada inteira:

```python
import array
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0,0]'), :v, COSINE) FROM DUAL",
              [array.array("f", [1, 0, 0])])
```

Retornar **só `(id, distância)`** e hidratar com o ORM — evita ler `RESPOSTA` NCLOB pelo cursor cru (onde `oracledb` devolve objeto LOB, não `str`) e deixa o repositório trivial de fakear em CI.

`reindexar_faq` `[S5-16]` idempotente por hash, não `DELETE`+insert como no spike.

### Bloco 4 — ChatService e SSE

| Fase | O que acontece | O que o usuário vê |
|---|---|---|
| 0 | `yield` imediato de `status` | "Pensando…" — derruba buffering de proxy e dá feedback antes de qualquer inferência |
| 1 | 1ª chamada **não-streaming** com `tools` | indicador continua |
| 2 | Executa tools; **renderiza o resultado como HTML** e emite | **cards de horário aparecem antes dos tokens** |
| 3 | Chamada final em streaming, `tool_choice="none"` | frase de conexão do LLM |
| 4 | Valida, grava `InteracaoChat`, `close` no `finally` | fontes do FAQ citadas |

> **A decisão de grounding mais importante: renderizar os dados no servidor, não no texto do LLM.** Quando `buscar_slots` retorna, o servidor já renderiza os cards com dados do banco, e o LLM só produz a frase em volta. Isso torna alucinação de horário **estruturalmente impossível** — é o único jeito confiável com um modelo de 4B, onde "NUNCA invente horários" no prompt é placebo. Bônus: os cards aparecem antes dos tokens, matando parte da espera.

O risco real com 4B não é inventar do zero — é **completar lacunas** ("e temos também às 14h") e **concordar com o usuário** ("então tem quinta às 15h, né?" → "Sim!").

**Validador pós-geração:** extrair `HH:MM`, `DD/MM` e nomes após "Dr./Dra." do texto; se algum não estiver no retorno das tools, marcar `alucinacao_detectada` e trocar por fallback seguro. Como não dá para desfazer o que já foi streamado, **validar em buffer antes de emitir** — com essa latência o streaming não está salvando nada mesmo, e é mais honesto. A taxa de detecção é o número que vai para a banca.

#### Cinco consertos sobre o código do spike

1. **`delta.reasoning`** — o spike faz `if not fragmento: continue` e descartaria tudo. Tratar como `status`, nunca como token. O campo **não existe no tipo `ChoiceDelta` do SDK** — acessar via `model_extra`.
2. **XSS** — htmx injeta o payload como HTML e a saída do LLM é conteúdo não confiável (prompt injection → `<img onerror=...>`). `django.utils.html.escape()` em cada fragmento. O spike só faz `.replace("\n"," ")`, que não protege nada.
3. **Newlines** — usar múltiplas linhas `data:` (o padrão SSE reconcatena com `\n`) em vez de destruir a formatação.
4. **Vazamento de erro** — o spike manda `str(exc)` para o browser, expondo DSN, usuário do Oracle e caminhos. Mandar mensagem amigável; stacktrace só no log.
5. **Reconexão do `EventSource`** — se o gerador estourar ou terminar sem `close`, o browser **refaz o GET em ~3s** e o LLM roda de novo, saturando o slot único do Ollama. POST cria a mensagem → stream é `GET /chat/stream/<uuid>/` → a view checa se já foi respondida e devolve `close` imediato.

#### Gotchas de Django

- **Não escrever na sessão dentro do gerador** — `SessionMiddleware.process_response` roda **antes** do gerador ser consumido; a escrita é silenciosamente perdida. É o que faz a **S5-2** ficar correta, não só "funcionando": gravar no POST, histórico em `InteracaoChat`.
- **Não adicionar `GZipMiddleware`** — bufferiza e mata o streaming.
- **Fechar o cursor Oracle antes de streamar** — com `CONN_MAX_AGE=0` o Django só libera a conexão quando o gerador termina; um stream de 40s segura a sessão Oracle 40s.
- **`max_tokens` é armadilha** — o thinking consome o orçamento e o `content` volta vazio, sem erro.
- **Contexto real é 4096**, não os 262144 anunciados. Com `--context-shift`, o Ollama descarta o início da conversa **silenciosamente, incluindo o system prompt com os guardrails**. Truncar o histórico e reenviar o system prompt sempre.
- **IDOR:** validar `conversa_id` contra a sessão, senão 404.
- Autoreload do `runserver` mata streams em curso — vai parecer bug e não é.

### Bloco 5 — Web

`views.py`, `urls.py`, `templates/chatbot/chat.html` estendendo `components/_layout.html`.

`runserver` **não** é o gargalo (é `ThreadingMixIn` sem pool limitado). O gargalo é o Ollama serial. **ASGI não é necessário agora** — mas fica o débito registrado: `gunicorn` com workers sync prende um worker inteiro por stream; em prod, `-k gthread --threads 16 --timeout 0` (sem timeout alto, o gunicorn mata o worker no meio do stream).

**Nenhuma mudança no Tailwind** — o glob `'../../**/templates/**/*.html'` já cobre `apps/chatbot/templates/`. Mas rodar `tailwind install` + `build` antes da demo: `apps/theme/static/css/` **não existe** hoje, então `{% tailwind_css %}` aponta para um arquivo inexistente e a página sai sem estilo.

Servir htmx/Alpine de `static/` em vez de CDN (bloqueada em rede corporativa, conforme o README do spike).

### Bloco 6 — Testes e fechamento

**CI (SQLite):** framing SSE, escape, filtro de CoT vazado — **é onde estão 80% dos bugs**. Mais o loop de tool use com `FakeLLMClient` (incluindo tool desconhecida, JSON de argumentos inválido, tool que estoura, 2 tool_calls no mesmo turno), tools contra ORM do SQLite, e a view.

**Local `@pytest.mark.oracle`:** vetor de 384 floats insere e de 383 falha (teste comportamental, robusto a nome de índice); índice existe (aceitar HNSW **ou** IVF — o fallback é válido); `buscar_semantica` com distância crescente; relevância `[S5-17]` assertando **ranking com tolerância**, nunca distância exata; `UK_SLOT_MEDICO_HORARIO` `[S1-11]`; migration aplica, faz rollback e reaplica.

**Local `@pytest.mark.llm`:** smoke de que "horários de retina" produz `tool_calls` com `buscar_slots` — canário contra regressão ao trocar de modelo.

**A resposta do LLM ponta a ponta não tem teste automatizado** — é não-determinística. Vira roteiro de demo.

Fechamento: atualizar [`STATUS.md`](STATUS.md), checkboxes das sprints, [`SETUP.md`](SETUP.md) com a seção Ollama, o ADR-0004 (Opção E → Decided) e ADRs novos para LLM local e para a coluna VECTOR fora do ORM — [`CONTRIBUTING.md`](../CONTRIBUTING.md) exige ADR para decisão arquitetural.

---

## 6. Verificação

```bash
docker stop $(docker ps -q --filter name=medreview)
```

```bash
ollama pull qwen3:4b-instruct-2507 && ollama pull all-minilm
```

Se a tag não existir no registry, usar `qwen2.5:3b-instruct`. **Não puxar o 8b** — não cabe nos 529 MiB de VRAM livres.

```bash
bash infra/scripts/bootstrap.sh
```

Sobe a stack e faz o restart que ativa o `vector_memory_size`. Primeiro boot leva 3-6 min. Conferir com `SHOW PARAMETER vector_memory_size`.

```bash
docker compose exec django python manage.py migrate
docker compose exec django python manage.py seed_initial
docker compose exec django python manage.py reindexar_faq
docker compose exec django pytest -m "not oracle and not llm" -q
docker compose exec django pytest -m oracle -q
```

**Teste manual — é o que define "funcional".** Abrir `http://localhost:8000/chat/` e validar os três caminhos da §1. Em todos: **a tela nunca fica parada mais de ~1s sem feedback**.

**Teste de grounding (R4):** perguntar por especialidade inexistente ("cardiologista") → precisa dizer que não atende, **sem inventar médico ou horário**. É o sinal de alerta que [`RISCOS.md`](RISCOS.md) define para esse risco.

**Instrumentar `ttf_content`** (tempo até o primeiro token visível) desde o primeiro dia — é a métrica que importa e a que engana se medida errado.

---

## 7. Três expectativas a corrigir

1. **`TTFT ≤ 2s` de [`METRICAS.md`](METRICAS.md) é inatingível** com LLM local, por uma ordem de grandeza (9,4s no caso bom). Redefinir a métrica por ambiente — *"≤ 15s com modelo local; ≤ 2s com provider gerenciado"* — e **registrar o número medido em vez de escondê-lo**. Para a banca, medir e explicar mostra mais rigor que uma meta furada.
2. **Streaming entrega pouco aqui.** Com 8-45s de silêncio *antes* do primeiro token e ~1s de geração depois, o que dá UX é o `event: status` e os cards renderizados pelo servidor — não a "animação suave de aparição dos tokens" `[S5-4]`, que pode ser despriorizada.
3. **"O spike validou tool use 3/3"** foi com o 8b. O teste com o 4b deu 6/6, então a conclusão se sustenta — mas os dois mediram coisas diferentes e **nenhum mediu o que quebra** (latência e thinking). Reaproveitar `03_tool_use_demo.py` como script de smoke, não como evidência.

---

## 8. Fora de escopo

Não entram nesta entrega: criação de Lead/Consulta `[S5-12]`, triagem oftalmológica `[S5-11]`, cancelamento `[S5-14]`, e-mails `[S5-29/30]`, rate limiting e anti-abuso `[S5-18..21]`, funil do CRM `[S5-22..25]`, cliente Anthropic real, e o restante da S1-8.

**Pendências que esta entrega cria e não fecha:** a dívida de revalidar tool use e streaming contra a Anthropic (débito #8 do STATUS) segue aberta — a interface `LLMClient` é onde ela será paga. Os gates de cobertura (#4) e do bandit (#5) seguem frouxos. ASGI fica como débito registrado.

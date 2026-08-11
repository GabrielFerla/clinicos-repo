# Setup do ClinicOS

Onboarding em 1 comando. Substitui as várias páginas de README "passo a passo" que normalmente travam novos devs no primeiro dia.

## Pré-requisitos

- **Docker** (Desktop em macOS/Windows, Engine em Linux/WSL2)
- **Docker Compose v2** (plugin do Docker; `docker compose version` deve responder)
- **Ollama no host**, para o chatbot (ver seção abaixo)

## Ollama — o LLM do chatbot

O chat roda com modelo local, sem chave de API e sem custo por token:

```bash
ollama pull qwen2.5:3b && ollama pull paraphrase-multilingual
```

Três coisas que economizam horas de depuração:

1. **Use um modelo sem "thinking".** Os da família qwen3 raciocinam antes de
   responder e isso **não desliga pela API** — nem por `think:false`, nem por
   `chat_template_kwargs`, nem por `/no_think`. O resultado é de 8 a 45 segundos
   de tela em branco, ou o raciocínio em inglês vazando como resposta.
2. **O modelo de embedding precisa ser multilíngue.** `all-minilm` é treinado em
   inglês e casa por sobreposição lexical em português — "que horas vocês
   abrem?" recuperava "Vocês atendem pelo SUS?".
3. **De dentro do container, o host é `host.docker.internal`** — o compose já
   injeta o `extra_hosts`. No Docker Desktop com WSL2 isso funciona mesmo com o
   Ollama escutando só em `127.0.0.1`. Confira com:
   ```bash
   docker compose run --rm django python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags',timeout=5).status)"
   ```

Medições e justificativas em [`CHAT_MVP.md`](CHAT_MVP.md).

Depois de `make migrate` e `make seed`, gere os embeddings — sem isso a busca
semântica não devolve nada:

```bash
docker compose run --rm django python manage.py reindexar_faq
```

## Portas

As portas publicadas no host são parametrizáveis, para a stack conviver com
outros projetos na mesma máquina. Redis e Mailhog já saem deslocados (6380 e
1026/8026). Para mudar, defina no `.env`: `ORACLE_PORT`, `DJANGO_PORT`,
`REDIS_PORT`, `MAILHOG_SMTP_PORT`, `MAILHOG_UI_PORT`.
- **`make`**
- ~6 GB de RAM livres para o container Oracle
- ~5 GB de disco para imagens + volume do Oracle
- Opcional, para rodar Django no host (fora do container): Python 3.12+

> Não precisa de Python no host. O ambiente Python é o container `django`.

## 1. Variáveis de ambiente

Copie o arquivo de exemplo e ajuste os valores:

```bash
cp .env.example .env
```

O `.env` está no `.gitignore` — **nunca** comite valores reais.

Para os helpers de criptografia (S1-13/S1-14), gere chaves novas:

```bash
python -c "import secrets; print('CPF_ENCRYPTION_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('CPF_HASH_PEPPER='   + secrets.token_urlsafe(32))"
```

Cole o resultado no `.env`. Em produção, essas chaves saem do secret manager (não do `.env`).

### Como o settings lê as variáveis

`config/settings/base.py` usa `django-environ`. A ordem de precedência é:

1. Variáveis exportadas no shell / injetadas pelo `docker-compose.yml`.
2. Arquivo `.env` na raiz do repo (carregado por `environ.Env.read_env`).
3. Defaults declarados no próprio `base.py`.

Dentro do container Docker, o compose já injeta `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, etc. — o `.env` é opcional. Fora do container (rodando `python manage.py ...` no host), o `.env` é a forma mais simples.

## 2. Subir tudo em 1 comando

```bash
make setup
```

Idempotente: pode rodar de novo sem medo. Se algo já existe (containers up, migrations aplicadas, superuser presente, `.env`), o passo é pulado.

### O que `make setup` faz

| # | Passo | Pode falhar? |
|---|---|---|
| 1 | Valida `docker` e `docker compose` no PATH | Sim — exige Docker instalado |
| 2 | Cria `.env` a partir de `.env.example` (se houver) | Não — apenas aviso se `.env.example` não existe |
| 3 | Chama `infra/scripts/bootstrap.sh` (sobe stack + restart Oracle p/ `vector_memory_size`) | Sim — se Oracle não ficar healthy em 5min |
| 4 | `python manage.py migrate --noinput` no container `django` | Sim — schema quebrado bloqueia |
| 5 | Roda `python manage.py seed_initial` (se o comando existir) | Não — passo opcional, vira aviso |
| 6 | Cria superuser `admin/admin` se não houver nenhum superuser | Não — apenas aviso |
| 7 | Imprime tabela com endpoints + credenciais | — |

### Tempo estimado

| Fase | Primeira vez | Re-execução |
|---|---|---|
| Build da imagem Django | ~3 min | cache: <5 s |
| Pull do Oracle 23ai (~3 GB) | ~5 min (rede dep.) | 0 |
| Boot inicial do Oracle | ~1 min | ~30 s |
| Restart do Oracle (vector_memory) | ~30 s | ~30 s |
| Migrate + superuser | ~10 s | <5 s |
| **Total** | **~10 min** (pior caso, sem cache) | **~1 min** |

> Em máquinas com Docker quente e imagens cacheadas, costuma ficar abaixo de 1 minuto.

## 3. Endpoints após o setup

| Serviço      | Endereço                       | Credenciais             |
|--------------|--------------------------------|-------------------------|
| Django       | http://localhost:8000          | -                       |
| Admin        | http://localhost:8000/admin/   | `admin` / `admin`       |
| Mailhog UI   | http://localhost:8025          | -                       |
| Mailhog SMTP | localhost:1025                 | -                       |
| Oracle 23ai  | localhost:1521 (svc FREEPDB1)  | `clinicos` / `oracle`   |
| Redis        | localhost:6379                 | -                       |

> `admin/admin` é apenas para dev local. **Troque** antes de qualquer ambiente compartilhado.

## 4. Comandos do dia-a-dia

```bash
make up        # Oracle 23ai + Redis + Mailhog + Django + Celery worker
make logs      # acompanha logs (Ctrl+C pra sair)
make down      # derruba tudo
make test      # pytest
make lint      # ruff + black --check
make fmt       # ruff --fix + black
```

## 5. Variáveis opcionais

Sobrescreva no shell antes do `make setup`:

| Var                | Default                  | Para que serve                          |
|--------------------|--------------------------|------------------------------------------|
| `DJANGO_SU_USER`   | `admin`                  | username do superuser criado             |
| `DJANGO_SU_EMAIL`  | `admin@clinicos.local`   | email do superuser                       |
| `DJANGO_SU_PASS`   | `admin`                  | senha do superuser                       |

## Troubleshooting

**Oracle não fica healthy**
Geralmente é RAM. O container precisa de ~4 GB. Conferir `docker stats clinicos-oracle`.

**`ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable`**
Faltou `DJANGO_SECRET_KEY` no `.env` (ou no shell). Confirme com `grep DJANGO_SECRET_KEY .env`.

**`oracledb.exceptions.OperationalError: DPY-6005`**
Django subiu antes do Oracle estar pronto. Espere o healthcheck (`docker compose ps`) ficar `(healthy)` e rode `docker compose restart django`.

**`make setup` quebra no migrate**
Veja os logs:
```bash
docker compose logs django oracle
```
Causas comuns: schema antigo no volume, app sem migration ainda (apps recém-criados podem precisar `makemigrations` antes).

**Quero zerar tudo**
```bash
make down
docker volume rm clinicos_oracle-data clinicos_redis-data  # cuidado: apaga banco
make setup
```

# Setup local (`make setup`)

Onboarding em 1 comando. Substitui as várias páginas de README "passo a passo" que normalmente travam novos devs no primeiro dia.

## Pré-requisitos

- **Docker** (Desktop em macOS/Windows, Engine em Linux/WSL2)
- **Docker Compose v2** (plugin do Docker; `docker compose version` deve responder)
- ~6 GB de RAM livres para o container Oracle
- ~5 GB de disco para imagens + volume do Oracle

> Não precisa de Python no host. O ambiente Python é o container `django`.

## Como rodar

```bash
make setup
```

Idempotente: pode rodar de novo sem medo. Se algo já existe (containers up, migrations aplicadas, superuser presente, `.env`), o passo é pulado.

## O que `make setup` faz

| # | Passo | Pode falhar? |
|---|---|---|
| 1 | Valida `docker` e `docker compose` no PATH | Sim — exige Docker instalado |
| 2 | Cria `.env` a partir de `.env.example` (se houver) | Não — apenas aviso se `.env.example` não existe |
| 3 | Chama `infra/scripts/bootstrap.sh` (sobe stack + restart Oracle p/ `vector_memory_size`) | Sim — se Oracle não ficar healthy em 5min |
| 4 | `python manage.py migrate --noinput` no container `django` | Sim — schema quebrado bloqueia |
| 5 | Roda `python manage.py seed_initial` (se o comando existir) | Não — passo opcional, vira aviso |
| 6 | Cria superuser `admin/admin` se não houver nenhum superuser | Não — apenas aviso |
| 7 | Imprime tabela com endpoints + credenciais | — |

## Tempo estimado

| Fase | Primeira vez | Re-execução |
|---|---|---|
| Build da imagem Django | ~3 min | cache: <5 s |
| Pull do Oracle 23ai (~3 GB) | ~5 min (rede dep.) | 0 |
| Boot inicial do Oracle | ~1 min | ~30 s |
| Restart do Oracle (vector_memory) | ~30 s | ~30 s |
| Migrate + superuser | ~10 s | <5 s |
| **Total** | **~10 min** (pior caso, sem cache) | **~1 min** |

> Em máquinas com Docker quente e imagens cacheadas, costuma ficar abaixo de 1 minuto.

## Endpoints após o setup

| Serviço      | Endereço                       | Credenciais             |
|--------------|--------------------------------|-------------------------|
| Django       | http://localhost:8000          | -                       |
| Admin        | http://localhost:8000/admin/   | `admin` / `admin`       |
| Mailhog UI   | http://localhost:8025          | -                       |
| Mailhog SMTP | localhost:1025                 | -                       |
| Oracle 23ai  | localhost:1521 (svc FREEPDB1)  | `clinicos` / `oracle`   |
| Redis        | localhost:6379                 | -                       |

> `admin/admin` é apenas para dev local. **Troque** antes de qualquer ambiente compartilhado.

## Troubleshooting

**Oracle não fica healthy**
Geralmente é RAM. O container precisa de ~4 GB. Conferir `docker stats clinicos-oracle`.

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

## Variáveis opcionais

Sobrescreva no shell antes do `make setup`:

| Var                | Default                  | Para que serve                          |
|--------------------|--------------------------|------------------------------------------|
| `DJANGO_SU_USER`   | `admin`                  | username do superuser criado             |
| `DJANGO_SU_EMAIL`  | `admin@clinicos.local`   | email do superuser                       |
| `DJANGO_SU_PASS`   | `admin`                  | senha do superuser                       |

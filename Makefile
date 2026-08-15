.PHONY: setup up down logs app worker shell test test-ci test-oracle test-llm lint fmt hooks-install \
        migrate makemigrations seed tailwind-install tailwind-dev tailwind-build

# Não há Python no host — tudo roda dentro do container `django`.
#
# `DJANGO_SETTINGS_MODULE` precisa ser forçado nos alvos de teste: o
# `environment:` do docker-compose define `config.settings.dev`, e variável de
# ambiente **vence** o `DJANGO_SETTINGS_MODULE` do pyproject.toml. Sem isso o
# pytest roda contra o Oracle em vez do SQLite em memória, e todo teste com
# banco falha (ou pior, escreve no banco de desenvolvimento).
DC       := docker compose
RUN      := $(DC) run --rm --no-deps django
# Prefixo sem o nome do serviço, para permitir acrescentar mais `-e` antes dele.
RUN_TEST_PRE := $(DC) run --rm --no-deps -e DJANGO_SETTINGS_MODULE=config.settings.test
RUN_TEST     := $(RUN_TEST_PRE) django

setup:             ; bash infra/scripts/setup.sh
up:                ; $(DC) up -d
down:              ; $(DC) down
logs:              ; $(DC) logs -f
app:               ; $(DC) up django
worker:            ; $(DC) up celery-worker
shell:             ; $(RUN) python manage.py shell

migrate:           ; $(DC) run --rm django python manage.py migrate
makemigrations:    ; $(RUN_TEST) python manage.py makemigrations
seed:              ; $(DC) run --rm django python manage.py seed_initial

# Suíte padrão: SQLite em memória, sem serviço externo. É o que o CI roda.
test:              ; $(RUN_TEST) pytest -q

# A suíte como o CI a enxerga: **sem `.env`**. Não é redundante com `test`.
# `config/settings/base.py` faz `read_env(BASE_DIR/".env")`, e o `.env` montado
# no container alimenta as settings — então `make test` pode ficar verde com
# variável que o CI não tem. Foi assim que 49 falhas e 104 erros passaram
# despercebidos até chegarem na `main`. Rode antes de abrir PR.
test-ci:           ; $(RUN_TEST) sh -c "cp -a /app /tmp/repo && rm -f /tmp/repo/.env && cd /tmp/repo && pytest -q"

# Testes que exigem serviço externo. Auto-pulados por padrão (ver conftest.py);
# as variáveis abaixo os habilitam.
test-oracle:       ; $(DC) run --rm -e CLINICOS_TEST_ORACLE=1 django pytest -q -m oracle
test-llm:          ; $(RUN_TEST_PRE) -e CLINICOS_TEST_LLM=1 django pytest -q -m llm

lint:              ; $(RUN) sh -c "ruff check . && black --check ."
fmt:               ; $(RUN) sh -c "ruff check --fix . && black ."
hooks-install:     ; pre-commit install

# Tailwind (django-tailwind, app apps.theme — ver S1-17 / docs/FRONTEND.md)
tailwind-install:  ; $(DC) run --rm django python manage.py tailwind install
tailwind-dev:      ; $(DC) run --rm django python manage.py tailwind start
tailwind-build:    ; $(DC) run --rm django python manage.py tailwind build

#!/usr/bin/env bash
# infra/scripts/setup.sh
#
# Onboarding em 1 comando para novos devs do ClinicOS.
#
# Uso:
#     ./infra/scripts/setup.sh
#     (ou, mais comum:)  make setup
#
# Idempotente: rodar 2x não quebra nada.
#   - containers já up → segue
#   - migration já aplicada → segue
#   - superuser já existe → pula (quem cuida disso é o seed_initial)
#   - .env já existe → pula
#
# Etapas:
#   1. Valida pré-requisitos (docker, docker compose)
#   2. Garante .env (cópia de .env.example se existir)
#   3. Sobe stack via infra/scripts/bootstrap.sh
#   4. Aplica migrations Django
#   5. Roda seed_initial — dados de demonstração **e** o superuser admin/admin
#   6. Compila o CSS do Tailwind (gitignorado: não vem pronto no clone)
#   7. Imprime endpoints úteis
#
# NÃO instala Python no host: o ambiente Python é o container `django`.

set -euo pipefail

# ----- helpers --------------------------------------------------------------

c_red()    { printf '\033[31m%s\033[0m\n' "$*"; }
c_green()  { printf '\033[32m%s\033[0m\n' "$*"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
c_blue()   { printf '\033[34m%s\033[0m\n' "$*"; }

step() { c_blue "[setup] $*"; }
warn() { c_yellow "[setup] aviso: $*"; }
ok()   { c_green  "[setup] ok: $*"; }
die()  { c_red    "[setup] ERRO: $*"; exit 1; }

# ----- entry ----------------------------------------------------------------

cd "$(dirname "$0")/../.."
REPO_ROOT="$(pwd)"
step "raiz do repo: ${REPO_ROOT}"

# ----- 1) pré-requisitos ----------------------------------------------------

step "validando pré-requisitos..."

if ! command -v docker >/dev/null 2>&1; then
  die "docker não encontrado no PATH. Instala Docker Desktop / Docker Engine antes."
fi

if ! docker --version >/dev/null 2>&1; then
  die "docker está no PATH mas não responde. Verifica o daemon (docker info)."
fi

# `docker compose` é plugin do Docker moderno; rejeitamos `docker-compose` v1.
if ! docker compose version >/dev/null 2>&1; then
  die "'docker compose' (v2 plugin) não disponível. Atualiza o Docker."
fi

ok "docker $(docker --version | awk '{print $3}' | tr -d ',') + compose $(docker compose version --short 2>/dev/null || echo 'v2')"

# ----- 2) .env --------------------------------------------------------------

step "garantindo .env..."

if [ -f ".env" ]; then
  ok ".env já existe (não sobrescrevo)"
elif [ -f ".env.example" ]; then
  cp -n .env.example .env || true
  ok ".env criado a partir de .env.example"
else
  warn ".env.example ainda não existe (provavelmente S1-7 não rodou). Seguindo sem .env."
fi

# ----- 3) bootstrap (sobe stack + restart Oracle) ---------------------------

step "subindo a stack (docker compose + restart Oracle para vector_memory_size)..."
bash "infra/scripts/bootstrap.sh"
ok "stack no ar"

# ----- 4) migrations --------------------------------------------------------

step "aplicando migrations..."
if docker compose exec -T django python manage.py migrate --noinput; then
  ok "migrations aplicadas"
else
  die "falha em manage.py migrate. Veja: docker compose logs django oracle"
fi

# ----- 5) seed (placeholder para S1-16) -------------------------------------

step "verificando seed inicial..."
# `manage.py help seed_initial` sai 0 se o comando existe, !=0 caso contrário.
if docker compose exec -T django python manage.py help seed_initial >/dev/null 2>&1; then
  step "rodando seed_initial..."
  if docker compose exec -T django python manage.py seed_initial; then
    ok "seed_initial rodou"
  else
    warn "seed_initial existe mas falhou; seguindo (não bloqueante neste estágio)."
  fi
else
  warn "management command 'seed_initial' ainda não existe (S1-16 cria); pulando."
fi

# ----- 6) CSS do Tailwind ---------------------------------------------------

# `apps/theme/static/css/dist/` é gitignorado, então quem clona o repo **nunca**
# recebe o CSS pronto. Sem este passo o `/chat/` abre como HTML cru — o
# `{% tailwind_css %}` do `base.html` aponta para um arquivo que não existe.
step "compilando o CSS (Tailwind)..."

if docker compose exec -T django python manage.py tailwind install; then
  if docker compose exec -T django python manage.py tailwind build; then
    # O restart não é zelo: o `AppDirectoriesFinder` monta a lista de pastas
    # `static/` **na subida** do processo, e `apps/theme/static/` só passa a
    # existir agora, no build acima. Sem reiniciar, o servidor que já está no ar
    # ignora o app inteiro e devolve 404 no CSS — página sem estilo, arquivo no
    # lugar certo, `findstatic` achando. Medido neste ambiente.
    docker compose restart django >/dev/null 2>&1 || warn "restart do django falhou"
    ok "CSS compilado"
  else
    warn "tailwind build falhou; as páginas abrirão sem estilo. Rode 'make tailwind-build'."
  fi
else
  warn "tailwind install falhou (npm no container?); pulando o build."
fi

# ----- 7) endpoints ---------------------------------------------------------

cat <<'EOTABLE'

================================================================================
  ClinicOS — ambiente pronto
================================================================================
  Serviço     | Endereço                          | Credenciais
  ------------|-----------------------------------|----------------------------
  Django      | http://localhost:8000             | admin / admin (TROQUE)
  Admin       | http://localhost:8000/admin/      | admin / admin
  Mailhog UI  | http://localhost:8025             | -
  Mailhog SMTP| localhost:1025                    | -
  Oracle 23ai | localhost:1521 (svc FREEPDB1)     | clinicos / oracle
  Redis       | localhost:6379                    | -
================================================================================

  Próximos passos:
    - make logs     # acompanhar logs
    - make test     # rodar suite pytest
    - make down     # derrubar tudo

EOTABLE

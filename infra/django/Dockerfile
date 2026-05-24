# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Pacotes de sistema mínimos:
#  - build-essential/libpq-dev: caso alguma wheel precise compilar
#  - curl/ca-certificates: healthchecks e downloads pontuais
#  - tini: PID 1 sane para o runserver/celery
# Sem Oracle Instant Client: o driver `oracledb` roda em thin mode
# (ADR-0001) e dispensa libs nativas.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Usuário não-root
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --system --gid ${APP_GID} app \
    && useradd --system --uid ${APP_UID} --gid ${APP_GID} \
        --home-dir /app --shell /bin/bash app

WORKDIR /app

# Instala requirements primeiro para aproveitar cache de camadas.
COPY infra/django/requirements /app/requirements
RUN pip install --upgrade pip \
    && pip install -r requirements/dev.txt

# Copia o restante do código (em dev este volume é sobrescrito pelo bind mount,
# mas a cópia mantém a imagem auto-suficiente para CI/prod).
COPY . /app

RUN chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

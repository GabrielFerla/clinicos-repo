#!/usr/bin/env bash
# infra/scripts/bootstrap.sh
#
# Sobe a stack ClinicOS pela primeira vez e garante que `vector_memory_size`
# fique ativo. O parâmetro é gravado no SPFILE pelos scripts em
# `infra/oracle-init/` e só vale no próximo startup — por isso o restart.
#
# Uso:
#     ./infra/scripts/bootstrap.sh
#
# Idempotente: rodar de novo apenas valida saúde dos serviços.

set -euo pipefail

cd "$(dirname "$0")/../.."

echo "[bootstrap] subindo serviços..."
docker compose up -d

echo "[bootstrap] aguardando Oracle ficar healthy (até 5 min)..."
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{.State.Health.Status}}' clinicos-oracle 2>/dev/null || echo "starting")
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 5
done

if [ "$status" != "healthy" ]; then
  echo "[bootstrap] Oracle não ficou healthy a tempo. Veja: docker compose logs oracle"
  exit 1
fi

echo "[bootstrap] reiniciando Oracle para aplicar vector_memory_size=512M..."
docker compose restart oracle

echo "[bootstrap] aguardando Oracle re-healthy..."
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{.State.Health.Status}}' clinicos-oracle 2>/dev/null || echo "starting")
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 5
done

if [ "$status" != "healthy" ]; then
  echo "[bootstrap] Oracle não voltou healthy após restart."
  exit 1
fi

echo "[bootstrap] pronto. Stack ClinicOS no ar."
echo "          Django:  http://localhost:8000"
echo "          Mailhog: http://localhost:8025"
echo "          Oracle:  localhost:1521 (user clinicos / pwd oracle / svc FREEPDB1)"

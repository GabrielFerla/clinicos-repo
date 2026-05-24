.PHONY: up down logs app worker test lint fmt hooks-install

up:             ; docker compose up -d
down:           ; docker compose down
logs:           ; docker compose logs -f
app:            ; python manage.py runserver 0.0.0.0:8000
worker:         ; celery -A clinicos worker -l info
test:           ; pytest -q
lint:           ; ruff check . && black --check .
fmt:            ; ruff check --fix . && black .
hooks-install:  ; pre-commit install

.PHONY: setup up down logs app worker test lint fmt hooks-install \
        tailwind-install tailwind-dev tailwind-build

setup:             ; bash infra/scripts/setup.sh
up:                ; docker compose up -d
down:              ; docker compose down
logs:              ; docker compose logs -f
app:               ; python manage.py runserver 0.0.0.0:8000
worker:            ; celery -A config worker -l info
test:              ; pytest -q
lint:              ; ruff check . && black --check .
fmt:               ; ruff check --fix . && black .
hooks-install:     ; pre-commit install

# Tailwind (django-tailwind, app apps.theme — ver S1-17 / docs/FRONTEND.md)
tailwind-install:  ; docker compose exec django python manage.py tailwind install
tailwind-dev:      ; docker compose exec django python manage.py tailwind start
tailwind-build:    ; docker compose exec django python manage.py tailwind build

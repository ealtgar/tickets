#!/usr/bin/env bash
# Arranque para producción (Render y similares).
# Aplica las migraciones pendientes y levanta Uvicorn en el puerto indicado.
set -euo pipefail

alembic upgrade head

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"

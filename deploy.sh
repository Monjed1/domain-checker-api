#!/usr/bin/env bash
set -euo pipefail

# Run on your VPS after cloning the project:
#   chmod +x deploy.sh && ./deploy.sh

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit API_KEY before exposing publicly."
fi

docker compose pull 2>/dev/null || true
docker compose build --no-cache
docker compose up -d

echo "API running on port 8000"
echo "Health: curl http://127.0.0.1:8000/health"
echo "Docs:   http://YOUR_SERVER_IP:8000/docs"

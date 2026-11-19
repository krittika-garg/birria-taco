#!/bin/bash
# Runs the API locally at http://127.0.0.1:8000, loading secrets from .env.

export CLOUD_MONGO=${CLOUD_MONGO:-0}
if [ -f .env ]; then set -a; . ./.env; set +a; fi

FLASK_APP=server.endpoints:create_app flask run --debug --host=127.0.0.1 --port=8000

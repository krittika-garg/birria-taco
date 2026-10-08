#!/bin/bash

export FLASK_ENV=development
export PROJ_DIR=$PWD
export DEBUG=1

# secrets (SECRET_KEY etc.) live in a gitignored .env:
if [ -f .env ]; then set -a; . ./.env; set +a; fi

# run our server locally:
PYTHONPATH=$(pwd):$PYTHONPATH
FLASK_APP=server.endpoints flask run --debug --host=127.0.0.1 --port=8000

#!/bin/bash
# Some common shell stuff.

echo "Importing from common.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SCRIPT_DIR")"

# MONGO_URI lives in the gitignored .env at the project root. A MONGO_URI
# already in the environment wins, so you can point a run elsewhere.
if [ -z "$MONGO_URI" ] && [ -f "$PROJ_ROOT/.env" ]; then set -a; . "$PROJ_ROOT/.env"; set +a; fi

DB=seDB
if [ -z "$DATA_DIR" ]
then
    DATA_DIR=$SCRIPT_DIR
fi
BKUP_DIR=$DATA_DIR/bkup
DUMP=$(command -v mongodump)
RESTORE=$(command -v mongorestore)

if [ -z "$MONGO_URI" ]
then
    echo "You must set MONGO_URI in your env (or .env) before running this script."
    exit 1
fi

if [ -z "$DUMP" ] || [ -z "$RESTORE" ]
then
    echo "mongodump/mongorestore not found; install the MongoDB Database Tools."
    exit 1
fi


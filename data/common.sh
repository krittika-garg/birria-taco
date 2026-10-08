#!/bin/bash
# Some common shell stuff.

echo "Importing from common.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SCRIPT_DIR")"

# MONGO_URI lives in the gitignored .env at the project root:
if [ -f "$PROJ_ROOT/.env" ]; then set -a; . "$PROJ_ROOT/.env"; set +a; fi

DB=seDB
if [ -z "$DATA_DIR" ]
then
    DATA_DIR=$SCRIPT_DIR
fi
BKUP_DIR=$DATA_DIR/bkup
EXP=$(command -v mongoexport)
IMP=$(command -v mongoimport)

if [ -z "$MONGO_URI" ]
then
    echo "You must set MONGO_URI in your env (or .env) before running this script."
    exit 1
fi

if [ -z "$EXP" ] || [ -z "$IMP" ]
then
    echo "mongoexport/mongoimport not found; install the MongoDB Database Tools."
    exit 1
fi

declare -a GameCollections=("users")

#!/bin/bash
# Restores the database from data/bkup/, replacing each backed-up collection.

. "$(dirname "$0")/common.sh"

"$RESTORE" --uri="$MONGO_URI" --drop --nsInclude="$DB.*" "$BKUP_DIR"

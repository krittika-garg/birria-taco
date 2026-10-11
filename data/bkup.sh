#!/bin/bash
# Script to backup production database to JSON files.

. "$(dirname "$0")/common.sh"

for collection in "${GameCollections[@]}"; do
    echo "Backing up $collection"
    $EXP --uri="$MONGO_URI" --db=$DB --collection=$collection --out=$BKUP_DIR/$collection.json
done

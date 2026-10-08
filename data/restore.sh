#!/bin/bash
# Script to restore production database from JSON backup files.

. "$(dirname "$0")/common.sh"

for collection in "${GameCollections[@]}"; do
    echo "Restoring $collection"
    $IMP --uri="$MONGO_URI" --db=$DB --collection $collection --drop --file $BKUP_DIR/$collection.json
done

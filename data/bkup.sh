#!/bin/bash
# Backs up every collection (and its indexes) in the database to data/bkup/.

. "$(dirname "$0")/common.sh"

"$DUMP" --uri="$MONGO_URI" --db=$DB --out="$BKUP_DIR"

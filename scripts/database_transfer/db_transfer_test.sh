#!/usr/bin/env bash

set -euo pipefail

# 0) Set absolute paths
PROJECT_ROOT="/home/rogerspyke/projects/robocoin-dataset"
SRC_DB="$PROJECT_ROOT/examples/database_transfer_test/ori_datasets.db"
DST_DB="$PROJECT_ROOT/examples/database_transfer_test/datasets_new.db"
SCRIPT="$PROJECT_ROOT/scripts/database_transfer/database_transfer.py"
CLEAR_SCRIPT="$PROJECT_ROOT/scripts/database_transfer/clear_target_db.py"

exists_table() {
  local db="$1"; shift
  local tbl="$1"; shift
  sqlite3 "$db" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='$tbl' LIMIT 1;" | grep -q 1
}

echo "[READ] Source tables:"
sqlite3 "$SRC_DB" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1;"

echo "[READ] Source 'datasets' count:"
sqlite3 "$SRC_DB" "SELECT COUNT(*) AS cnt FROM datasets;"

if exists_table "$SRC_DB" "lerobot_format_convert"; then
  echo "[READ] Source 'lerobot_format_convert' count:"
  sqlite3 "$SRC_DB" "SELECT COUNT(*) AS cnt FROM lerobot_format_convert;"
else
  echo "[READ] Optional table 'lerobot_format_convert' not found in source; skipping count"
fi

if exists_table "$SRC_DB" "lerobot_format_convert_test"; then
  echo "[READ] Source 'lerobot_format_convert_test' count:"
  sqlite3 "$SRC_DB" "SELECT COUNT(*) AS cnt FROM lerobot_format_convert_test;"
else
  echo "[READ] Optional table 'lerobot_format_convert_test' not found in source; skipping count"
fi

# 1) (Optional) Show a checksum of the source DB to verify it remains unchanged after transfer
sha256sum "$SRC_DB"

# 2) Destination pre-checks (file and table)
if [[ -f "$DST_DB" ]]; then
  echo "[READ] Destination DB exists: $DST_DB"
else
  echo "[ERROR] Destination DB does not exist: $DST_DB"
  echo "[HINT] Create the DB and its 'datasets' table first."
  exit 1
fi

if exists_table "$DST_DB" "datasets"; then
  echo "[READ] Destination 'datasets' exists; current row count:"
  sqlite3 "$DST_DB" "SELECT COUNT(*) AS cnt FROM datasets;"
else
  echo "[ERROR] Destination does not contain table 'datasets'"
  echo "[HINT] Create 'datasets' table schema beforehand; the transfer script won't modify schema."
  exit 1
fi

# 3) Run transfer with explicit paths; preview 5 rows
python "$SCRIPT" --source-db "$SRC_DB" --dest-db "$DST_DB" --show 5 -v

# 4) Post-check destination 'datasets'
echo "[READ] Destination 'datasets' schema:"
sqlite3 "$DST_DB" "PRAGMA table_info(datasets);"
echo "[READ] Destination 'datasets' count after transfer:"
sqlite3 "$DST_DB" "SELECT COUNT(*) AS cnt FROM datasets;"

# 5) Verify the source DB was not modified (checksum should match)
sha256sum "$SRC_DB"

# 6) Idempotency test: run again
python "$SCRIPT" --source-db "$SRC_DB" --dest-db "$DST_DB" --show 3 -v

echo "[NOTE] The transfer script only writes overlapping columns into destination 'datasets'."

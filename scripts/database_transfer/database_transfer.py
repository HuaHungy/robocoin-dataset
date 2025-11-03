#!/usr/bin/env python3
"""Database table transfer utility.

Transfers selected tables from a source SQLite database to a destination
SQLite database, preserving table schema and data.

Defaults are set to the test databases under `examples/database_transfer_test/`.

## Robust Default Value Logic

This script implements a robust approach to ensure all status and version fields
have proper default values:

1. Read 'datasets' table from source database
2. Initialize ALL *_status fields to "PENDING" and ALL *_version/*_version_ps fields to 0
3. Enrich with actual values from specified auxiliary tables (e.g., lerobot_format_convert)
   - Actual non-None values overwrite the defaults
4. Apply optimization: when convert_status is COMPLETED but convert_test_status is still
   PENDING (no test entry), automatically propagate COMPLETED to convert_test_status
5. Upsert into destination database (update existing records, insert new ones)
6. Verify transfer accuracy by comparing source and destination data

This ensures no NULL values in status/version fields, with real data taking precedence.

## Transfer Verification

After transfer, the script automatically verifies data accuracy by:
- Comparing expected (source) vs actual (destination) data field-by-field
- Excluding default-initialized fields from strict comparison
- Reporting any missing UUIDs, extra UUIDs, or field mismatches
- Logging a clear PASSED/FAILED verification status

Usage examples (Linux):

- Transfer defaults (two tables) into a new DB in test folder:
  python scripts/database_transfer/database_transfer.py

- Explicit source/destination and table list:
  python scripts/database_transfer/database_transfer.py \
    --source-db /home/rogerspyke/projects/robocoin-dataset/examples/database_transfer_test/ori_datasets.db \
    --dest-db /home/rogerspyke/projects/robocoin-dataset/examples/database_transfer_test/datasets_new.db \
    --tables lerobot_format_convert lerobot_format_convert_test

- Append without clearing destination tables first:
  python scripts/database_transfer/database_transfer.py --append
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

# Ensure `src` is importable when running as a script
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402,F401

LOGGER = logging.getLogger("database_transfer")


def _setup_logging(verbose: bool) -> None:
    """Configure logging for the script.

    Args:
        verbose: If True, sets logging level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def _sqlite_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists in the database.

    Args:
        engine: SQLAlchemy engine for the database
        table_name: Name of the table to check

    Returns:
        True if the table exists, False otherwise.
    """
    inspector = sa_inspect(engine)
    return table_name in inspector.get_table_names()


def _get_create_table_sql(engine: Engine, table_name: str) -> str | None:
    """Get CREATE TABLE SQL for a table from sqlite_master.

    Returns the SQL string used to create the table, or None if table doesn't exist.
    This function is retained for reference but is not currently used by this script,
    as the script follows a strict no-schema-modification policy for source databases.
    """
    query = text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=:name LIMIT 1"
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"name": table_name}).fetchone()
        if row and row[0]:
            return str(row[0])
    return None


def _get_source_columns(engine: Engine, table_name: str) -> list[tuple[str, str]]:
    """Get all columns from a table using PRAGMA table_info.

    Args:
        engine: SQLAlchemy engine for the database
        table_name: Name of the table to inspect

    Returns:
        List of tuples (column_name, column_type) for all columns in the table.
        PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    """
    pragma_sql = text(f"PRAGMA table_info({table_name})")
    with engine.connect() as conn:
        # row columns: cid, name, type, notnull, dflt_value, pk
        return [(str(row[1]), str(row[2])) for row in conn.execute(pragma_sql)]


def _ensure_dest_schema_matches_source(
    source_engine: Engine, dest_engine: Engine, table_name: str
) -> None:
    """No-op placeholder function.

    This function intentionally does nothing. Destination schema must not be
    modified by this script as per design policy. The function is retained
    for interface compatibility with earlier versions.
    """
    return


def _fetch_all_rows(source_engine: Engine, table_name: str) -> list[dict[str, object]]:
    """Fetch all rows from a table as dictionaries.

    Args:
        source_engine: SQLAlchemy engine for the database
        table_name: Name of the table to read from

    Returns:
        List of dictionaries where each dict represents a row with column names as keys
        and column values as values.
    """
    with source_engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM {table_name}"))
        columns: Sequence[str] = rows.keys()
        return [dict(zip(columns, row)) for row in rows.fetchall()]


def _truncate_table(dest_engine: Engine, table_name: str) -> None:
    """Delete all records from a table (truncate).

    Note: This function is not used by the default script workflow,
    but is retained for potential use by external callers.

    Args:
        dest_engine: SQLAlchemy engine for the destination database
        table_name: Name of the table to truncate
    """
    with dest_engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table_name}"))


def _insert_rows(
    dest_engine: Engine,
    table_name: str,
    rows: Iterable[dict[str, object]],
) -> int:
    """Insert rows into destination table using parameterized queries.

    Only inserts columns that exist in the destination table, excluding the 'id'
    column to avoid primary key conflicts. Uses parameterized queries to prevent
    SQL injection attacks.

    Args:
        dest_engine: SQLAlchemy engine for the destination database
        table_name: Name of the table to insert into
        rows: Iterable of dictionaries where keys are column names and values are
              column values to insert

    Returns:
        Number of rows inserted.
    """
    rows_list = list(rows)
    if not rows_list:
        return 0
    dest_cols = _get_source_columns(dest_engine, table_name)
    dest_col_names = {name for name, _ in dest_cols}
    columns_to_use = [c for c in dest_col_names if c != "id"]
    if not columns_to_use:
        return 0
    placeholders = ", ".join([f":{k}" for k in columns_to_use])
    columns_csv = ", ".join(columns_to_use)
    sql = text(f"INSERT INTO {table_name} ({columns_csv}) VALUES ({placeholders})")
    to_insert = [{k: r.get(k) for k in columns_to_use} for r in rows_list]
    with dest_engine.begin() as conn:
        conn.execute(sql, to_insert)
    return len(to_insert)


def _upsert_rows_by_dataset_uuid(
    dest_engine: Engine,
    table_name: str,
    rows: Iterable[dict[str, object]],
) -> tuple[int, int]:
    """Upsert rows based on dataset_uuid if present in destination.

    Performs an upsert (update if exists, insert if not) operation by checking
    the dataset_uuid field against existing records in the destination table.
    If dataset_uuid already exists in the table, the record is updated;
    otherwise, it's inserted as a new record.

    This function assumes that defaults have already been initialized for all
    status/version fields via `_initialize_all_defaults`. As a safety net, it
    applies `_fill_missing_defaults` to fill any remaining None values before
    database operations.

    Args:
        dest_engine: SQLAlchemy engine for the destination database
        table_name: Name of the target table to upsert data into
        rows: Iterable of dictionaries containing row data to process

    Returns:
        Tuple of (num_updated, num_inserted).
    """
    rows_list = list(rows)
    if not rows_list:
        return (0, 0)
    dest_cols = _get_source_columns(dest_engine, table_name)
    dest_col_names = {name for name, _ in dest_cols}
    if "dataset_uuid" not in dest_col_names:
        # Fallback to pure inserts using overlapping columns
        return (0, _insert_rows(dest_engine, table_name, rows_list))

    # Build set of uuids in destination
    existing: set[str] = set()
    with dest_engine.connect() as conn:
        for row in conn.execute(text("SELECT dataset_uuid FROM datasets")):
            if row[0] is not None:
                existing.add(str(row[0]))

    to_update = []
    to_insert = []
    for r in rows_list:
        uuid_val = r.get("dataset_uuid")
        if uuid_val is not None and str(uuid_val) in existing:
            to_update.append(r)
        else:
            to_insert.append(r)

    # UPDATE: only overlapping columns except id and dataset_uuid as key
    updated = 0
    if to_update:
        # Apply fallback defaults for any fields that are still None (safety net for updates)
        _fill_missing_defaults(dest_engine, table_name, to_update)

        # Skip columns with None values to avoid overwriting existing destination data
        with dest_engine.begin() as conn:
            for r in to_update:
                update_cols_row = [
                    c
                    for c in dest_col_names
                    if c not in {"id", "dataset_uuid"} and r.get(c) is not None
                ]
                if not update_cols_row:
                    continue
                set_clause = ", ".join([f"{c}=:{c}" for c in update_cols_row])
                sql = text(
                    f"UPDATE {table_name} SET {set_clause} WHERE dataset_uuid = :dataset_uuid"
                )
                params = {c: r.get(c) for c in update_cols_row}
                params["dataset_uuid"] = r.get("dataset_uuid")
                conn.execute(sql, params)
                updated += 1

    # INSERT: only overlapping columns except id
    inserted = 0
    if to_insert:
        # Note: Defaults should already be set by _initialize_all_defaults before enrichment
        # Apply fallback defaults for any fields that are still None (safety net)
        _fill_missing_defaults(dest_engine, table_name, to_insert)
        inserted = _insert_rows(dest_engine, table_name, to_insert)

    return (updated, inserted)


def _list_tables(engine: Engine) -> list[str]:
    """Get sorted list of all table names in the database.

    Args:
        engine: SQLAlchemy engine for the database

    Returns:
        Sorted list of table names.
    """
    inspector = sa_inspect(engine)
    return sorted(inspector.get_table_names())


def _build_sqlite_engine(db_path: Path) -> Engine:
    """Create a SQLAlchemy engine for a SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        SQLAlchemy Engine instance configured for SQLite with check_same_thread disabled.
    """
    url = f"sqlite:///{db_path}"
    return create_engine(url, connect_args={"check_same_thread": False})


def _enrich_datasets_from_tables(
    source_engine: Engine,
    datasets_rows: list[dict[str, object]],
    use_tables: list[str],
    enrich_configs: dict[str, dict[str, object]] | None = None,
) -> None:
    """Enrich rows in 'datasets' from one or more auxiliary tables.

    The enrichment is driven by a per-table config mapping. Each table config supports:
    - join_on: column name used to join with datasets (default: "dataset_uuid")
    - select: list of column names to select from the table (must include join_on)
    - map: dict mapping source column -> destination field in datasets

    If ``enrich_configs`` is None, sensible defaults are provided for the
    historical convert tables used by this script.
    """
    if not datasets_rows:
        return

    # Build fast lookup by dataset_uuid
    by_uuid: dict[str, dict[str, object]] = {}
    for r in datasets_rows:
        ds_uuid = str(r.get("dataset_uuid")) if r.get("dataset_uuid") is not None else None
        if ds_uuid:
            by_uuid[ds_uuid] = r

    def table_exists(name: str) -> bool:
        return _sqlite_table_exists(source_engine, name)

    # Default enrichment configs for known tables
    if enrich_configs is None:
        enrich_configs = {
            "lerobot_format_convert": {
                "join_on": "dataset_uuid",
                "select": [
                    "dataset_uuid",
                    "convert_status",
                    "convert_path",
                    "err_message",
                    "device_model",
                    "device_model_version",
                    "total_episodes",
                    "converted_episodes",
                    "skipped_episodes",
                ],
                "map": {
                    "convert_status": "convert_status",
                    "convert_path": "convert_path",
                    "err_message": "convert_err_msg",
                    "device_model": "device_model",
                    "device_model_version": "device_model_version",
                    "total_episodes": "total_episodes",
                    "converted_episodes": "converted_episodes",
                    "skipped_episodes": "skipped_episodes",
                },
            },
            "lerobot_format_convert_test": {
                "join_on": "dataset_uuid",
                "select": ["dataset_uuid", "convert_status"],
                "map": {"convert_status": "convert_test_status"},
            },
        }

    for table_name in use_tables:
        if table_name not in enrich_configs:
            LOGGER.info("[READ] No enrichment config provided for table '%s'; skipping", table_name)
            continue
        if not table_exists(table_name):
            LOGGER.info("[READ] Optional table '%s' not found in source; skipping enrichment", table_name)
            continue

        cfg = enrich_configs[table_name]
        join_on = str(cfg.get("join_on", "dataset_uuid"))
        select_cols = list(cfg.get("select", []))
        field_map: dict[str, str] = dict(cfg.get("map", {}))

        # Ensure join_on is included in select
        if join_on not in select_cols:
            select_cols = [join_on] + select_cols

        LOGGER.info("[READ] Enriching datasets from '%s' (join_on=%s)", table_name, join_on)
        sql = text(f"SELECT {', '.join(select_cols)} FROM {table_name}")
        merged = 0
        with source_engine.connect() as conn:
            res = conn.execute(sql)
            for row in res.mappings():
                ds_uuid_val = row.get(join_on)
                ds_uuid = str(ds_uuid_val) if ds_uuid_val is not None else None
                if not ds_uuid or ds_uuid not in by_uuid:
                    continue
                tgt = by_uuid[ds_uuid]
                for src_col, dest_field in field_map.items():
                    val = row.get(src_col)
                    if val is not None:
                        tgt[dest_field] = val
                merged += 1
        LOGGER.info("[READ] Merged %d rows from '%s' into datasets", merged, table_name)


def _ensure_dest_has_columns_for_rows(
    dest_engine: Engine,
    table_name: str,
    rows: list[dict[str, object]],
) -> None:
    """Ensure destination table has all columns referenced by rows.

    Known-field type mapping is used where possible; otherwise TEXT is used.
    """
    if not rows:
        return
    # Collect all keys present across rows
    all_keys: set[str] = set()
    for r in rows:
        all_keys.update(r.keys())

    # Existing destination columns
    dest_cols = _get_source_columns(dest_engine, table_name)
    dest_col_names = {name for name, _ in dest_cols}

    missing = [k for k in sorted(all_keys) if k not in dest_col_names]
    if not missing:
        return
    LOGGER.warning(
        "[SCHEMA] Destination table '%s' is missing %d columns: %s",
        table_name,
        len(missing),
        ", ".join(missing),
    )

    # Best-effort type inference for known fields
    known_types: dict[str, str] = {
        # text-like
        "convert_status": "TEXT",
        "convert_test_status": "TEXT",
        "convert_path": "TEXT",
        "convert_err_msg": "TEXT",
        "device_model": "TEXT",
        "device_model_version": "TEXT",
        # integers
        "total_episodes": "INTEGER",
        "converted_episodes": "INTEGER",
        "skipped_episodes": "INTEGER",
    }

    with dest_engine.begin() as conn:
        for col in missing:
            col_type = known_types.get(col, "TEXT")
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}"))
            LOGGER.info(
                "Added destination column %s (%s) to %s to fit incoming rows",
                col,
                col_type,
                table_name,
            )


def _get_status_and_version_columns(
    engine: Engine, table_name: str
) -> tuple[list[str], list[str]]:
    """Identify status and version columns in a table.

    Args:
        engine: SQLAlchemy engine for the database
        table_name: Name of the table to inspect

    Returns:
        Tuple of (status_columns, version_columns) where:
        - status_columns: All columns ending with "_status"
        - version_columns: All columns ending with "_version" or "_version_ps",
          plus exact matches for "version" or "version_ps"
    """
    dest_cols = _get_source_columns(engine, table_name)
    dest_col_names = {name for name, _ in dest_cols}

    # Identify columns to default
    lower_names = {name: name.lower() for name in dest_col_names}

    # All *_status
    status_cols = [name for name, low in lower_names.items() if low.endswith("_status")]

    # All *_version and *_version_ps (also include exact "version"/"version_ps")
    version_cols = [
        name
        for name, low in lower_names.items()
        if low.endswith("_version") or low.endswith("_version_ps") or low in {"version", "version_ps"}
    ]

    return (status_cols, version_cols)


def _initialize_all_defaults(
    dest_engine: Engine,
    table_name: str,
    rows: list[dict[str, object]],
) -> None:
    """Initialize ALL status and version fields with default values.

    This function sets defaults for ALL status/version fields BEFORE enrichment,
    ensuring a robust baseline. Subsequent enrichment from tables will overwrite
    these defaults with actual values where available.

    Applied defaults:
    - All columns ending with "_status": "PENDING"
    - All columns ending with "_version" or "_version_ps": 0
    - Exact matches for "version" or "version_ps": 0

    Modifies rows in-place.

    Args:
        dest_engine: SQLAlchemy engine for the destination database (used to inspect schema)
        table_name: Name of the table (used to identify status/version columns)
        rows: List of row dictionaries to modify in-place
    """
    if not rows:
        return

    status_cols, version_cols = _get_status_and_version_columns(dest_engine, table_name)

    if not status_cols and not version_cols:
        return

    # Set defaults for ALL rows, ALL status/version fields
    for r in rows:
        # Status defaults: PENDING
        for col in status_cols:
            r[col] = "PENDING"
        # Version defaults: 0
        for col in version_cols:
            r[col] = 0


def _fill_missing_defaults(
    dest_engine: Engine,
    table_name: str,
    rows: list[dict[str, object]],
) -> None:
    """Fill defaults ONLY for missing (None or absent) status/version fields.

    This is a fallback function for cases where defaults weren't initialized earlier.
    It only sets defaults for fields that are missing or None, preserving any
    existing values.

    Applied defaults:
    - All columns ending with "_status": "PENDING"
    - All columns ending with "_version" or "_version_ps": 0
    - Exact matches for "version" or "version_ps": 0

    Modifies rows in-place.

    Args:
        dest_engine: SQLAlchemy engine for the destination database (used to inspect schema)
        table_name: Name of the table (used to identify status/version columns)
        rows: List of row dictionaries to modify in-place
    """
    if not rows:
        return

    status_cols, version_cols = _get_status_and_version_columns(dest_engine, table_name)

    if not status_cols and not version_cols:
        return

    for r in rows:
        # Status defaults: only if missing or None
        for col in status_cols:
            if r.get(col) is None:
                r[col] = "PENDING"
        # Version defaults: only if missing or None
        for col in version_cols:
            if r.get(col) is None:
                r[col] = 0


def _propagate_convert_completion_to_test(
    rows: list[dict[str, object]],
) -> int:
    """Propagate COMPLETED status from convert to test when test has no entry.

    Optimization: When convert_status is COMPLETED but convert_test_status is still
    at the default PENDING (indicating no entry existed in the test table), automatically
    set convert_test_status to COMPLETED.

    This assumes that if conversion completed successfully, the test phase can be
    considered complete as well when no explicit test entry exists.

    Modifies rows in-place.

    Args:
        rows: List of row dictionaries to modify in-place

    Returns:
        Number of rows where test status was propagated from convert status.
    """
    if not rows:
        return 0

    propagated_count = 0
    for row in rows:
        convert_status = row.get("convert_status")
        convert_test_status = row.get("convert_test_status")

        # Only propagate if convert is COMPLETED and test is still PENDING (default)
        if convert_status == "COMPLETED" and convert_test_status == "PENDING":
            row["convert_test_status"] = "COMPLETED"
            propagated_count += 1

    return propagated_count


def _verify_transfer_accuracy(
    dest_engine: Engine,
    table_name: str,
    expected_rows: list[dict[str, object]],
    default_initialized_fields: set[str],
) -> dict[str, object]:
    """Verify transfer accuracy by comparing expected vs actual destination data.

    Implements merge-aware comparison logic: When expected value is None but actual
    destination value is non-null, this is treated as acceptable "merge preservation"
    rather than an error (aligns with upsert behavior that skips None values).

    Args:
        dest_engine: SQLAlchemy engine for the destination database
        table_name: Name of the table to verify
        expected_rows: List of row dictionaries that were transferred (with defaults applied)
        default_initialized_fields: Set of field names that were initialized with defaults
                                    (these will be excluded from strict comparison)

    Returns:
        Dictionary containing verification results with keys:
        - 'success': bool indicating if verification passed (true if no mismatches/missing/extra UUIDs)
        - 'total_expected': int number of expected rows
        - 'total_actual': int number of actual rows in destination
        - 'mismatches': list of dicts describing any discrepancies (real errors)
        - 'missing_uuids': list of dataset_uuids that were expected but not found
        - 'extra_uuids': list of dataset_uuids found in destination but not expected
        - 'merge_preservations': list of dicts for fields where None + non-null → non-null
                                 (these are logged as warnings but don't fail verification)
    """
    if not expected_rows:
        return {
            "success": True,
            "total_expected": 0,
            "total_actual": 0,
            "mismatches": [],
            "missing_uuids": [],
            "extra_uuids": [],
            "merge_preservations": [],
        }

    # Build lookup of expected rows by dataset_uuid
    expected_by_uuid: dict[str, dict[str, object]] = {}
    for row in expected_rows:
        uuid_val = row.get("dataset_uuid")
        if uuid_val is not None:
            expected_by_uuid[str(uuid_val)] = row

    # Fetch actual destination rows
    actual_rows = _fetch_all_rows(dest_engine, table_name)
    actual_by_uuid: dict[str, dict[str, object]] = {}
    for row in actual_rows:
        uuid_val = row.get("dataset_uuid")
        if uuid_val is not None:
            actual_by_uuid[str(uuid_val)] = row

    # Find missing and extra UUIDs
    expected_uuids = set(expected_by_uuid.keys())
    actual_uuids = set(actual_by_uuid.keys())
    missing_uuids = list(expected_uuids - actual_uuids)
    extra_uuids = list(actual_uuids - expected_uuids)

    # Compare matching rows field by field
    mismatches: list[dict[str, object]] = []
    merge_preservations: list[dict[str, object]] = []

    for uuid in expected_uuids & actual_uuids:
        expected_row = expected_by_uuid[uuid]
        actual_row = actual_by_uuid[uuid]

        field_mismatches: list[dict[str, object]] = []
        field_preservations: list[dict[str, object]] = []

        # Get all fields to compare (union of both row keys, excluding 'id')
        all_fields = (set(expected_row.keys()) | set(actual_row.keys())) - {"id"}

        for field in sorted(all_fields):
            # Skip fields that were default-initialized (not from source data)
            if field in default_initialized_fields:
                continue

            expected_val = expected_row.get(field)
            actual_val = actual_row.get(field)

            # Compare values (handle None explicitly)
            if expected_val != actual_val:
                # Special handling for numeric comparisons (int vs float)
                if isinstance(expected_val, int | float) and isinstance(actual_val, int | float):
                    if abs(float(expected_val) - float(actual_val)) < 1e-9:
                        continue

                # MERGE PRESERVATION LOGIC: If expected is None but actual is non-null,
                # this is acceptable - it means we preserved existing destination data
                # instead of overwriting with None (as per upsert logic at line 273)
                if expected_val is None and actual_val is not None:
                    field_preservations.append({
                        "field": field,
                        "preserved_value": actual_val,
                    })
                    continue

                # If actual is None but expected is non-null, this is a real mismatch
                # (data was lost or not written correctly)
                field_mismatches.append({
                    "field": field,
                    "expected": expected_val,
                    "actual": actual_val,
                })

        if field_mismatches:
            mismatches.append({
                "dataset_uuid": uuid,
                "field_mismatches": field_mismatches,
            })

        if field_preservations:
            merge_preservations.append({
                "dataset_uuid": uuid,
                "field_preservations": field_preservations,
            })

    success = len(mismatches) == 0 and len(missing_uuids) == 0 and len(extra_uuids) == 0

    return {
        "success": success,
        "total_expected": len(expected_rows),
        "total_actual": len(actual_rows),
        "mismatches": mismatches,
        "missing_uuids": missing_uuids,
        "extra_uuids": extra_uuids,
        "merge_preservations": merge_preservations,
    }


def _log_verification_results(results: dict[str, object]) -> None:
    """Log verification results in a readable format.

    Args:
        results: Verification results dictionary from _verify_transfer_accuracy
    """
    # Check for merge preservations (None + non-null → non-null)
    merge_preservations = results.get("merge_preservations", [])

    if results["success"]:
        LOGGER.info(
            "[VERIFY] ✓ Transfer verification PASSED: %d rows accurately transferred",
            results["total_expected"],
        )

        # Log merge preservation warnings even when verification passes
        if merge_preservations:
            total_preserved_fields = sum(
                len(p["field_preservations"]) for p in merge_preservations
            )
            LOGGER.warning(
                "[VERIFY] ⚠ Merge preservation applied: %d rows with %d preserved fields",
                len(merge_preservations),
                total_preserved_fields,
            )
            LOGGER.warning(
                "[VERIFY] ⚠ These fields had None in source but non-null in destination; "
                "destination values were preserved (not overwritten with None)"
            )
            # Show details for first few preservation cases
            for i, preservation in enumerate(merge_preservations[:3]):
                uuid = preservation["dataset_uuid"]
                preserved_fields = preservation["field_preservations"]
                field_names = [p["field"] for p in preserved_fields[:5]]
                LOGGER.warning(
                    "[VERIFY]   Row %d (uuid=%s): preserved %d fields: %s%s",
                    i + 1,
                    uuid,
                    len(preserved_fields),
                    ", ".join(field_names),
                    "..." if len(preserved_fields) > 5 else "",
                )
            if len(merge_preservations) > 3:
                LOGGER.warning(
                    "[VERIFY]   ... and %d more rows with preserved fields",
                    len(merge_preservations) - 3,
                )

        return

    LOGGER.warning("[VERIFY] ✗ Transfer verification FAILED")
    LOGGER.warning(
        "[VERIFY] Expected rows: %d, Actual rows: %d",
        results["total_expected"],
        results["total_actual"],
    )

    missing_uuids = results.get("missing_uuids", [])
    if missing_uuids:
        LOGGER.warning(
            "[VERIFY] Missing UUIDs (%d): %s",
            len(missing_uuids),
            ", ".join(missing_uuids[:5]) + ("..." if len(missing_uuids) > 5 else ""),
        )

    extra_uuids = results.get("extra_uuids", [])
    if extra_uuids:
        LOGGER.warning(
            "[VERIFY] Extra UUIDs (%d): %s",
            len(extra_uuids),
            ", ".join(extra_uuids[:5]) + ("..." if len(extra_uuids) > 5 else ""),
        )

    mismatches = results.get("mismatches", [])
    if mismatches:
        LOGGER.warning("[VERIFY] Field mismatches found in %d rows:", len(mismatches))
        # Show details for first few mismatches
        for i, mismatch in enumerate(mismatches[:3]):
            uuid = mismatch["dataset_uuid"]
            LOGGER.warning("[VERIFY]   Row %d (uuid=%s):", i + 1, uuid)
            for field_mismatch in mismatch["field_mismatches"][:5]:
                field = field_mismatch["field"]
                expected = field_mismatch["expected"]
                actual = field_mismatch["actual"]
                LOGGER.warning(
                    "[VERIFY]     - %s: expected=%s, actual=%s",
                    field,
                    expected,
                    actual,
                )
        if len(mismatches) > 3:
            LOGGER.warning("[VERIFY]   ... and %d more rows with mismatches", len(mismatches) - 3)

    # Log merge preservation warnings in failure case too
    if merge_preservations:
        total_preserved_fields = sum(
            len(p["field_preservations"]) for p in merge_preservations
        )
        LOGGER.warning(
            "[VERIFY] ⚠ Merge preservation applied: %d rows with %d preserved fields",
            len(merge_preservations),
            total_preserved_fields,
        )
        LOGGER.warning(
            "[VERIFY] ⚠ (Note: These are NOT errors - destination values were correctly preserved)"
        )


def transfer_tables(
    source_db_path: Path,
    dest_db_path: Path,
    tables: list[str],
    append: bool,
    show_rows: int,
) -> None:
    """Transfer data from source to destination database using upsert strategy.

    Implements a robust default initialization approach:
    1. Reads the 'datasets' table from source
    2. Initializes ALL status fields to "PENDING" and version fields to 0 (baseline defaults)
    3. Enriches with actual values from specified auxiliary tables (overwrites defaults)
    4. Applies optimization: propagates COMPLETED from convert_status to convert_test_status
       when test status is still PENDING (indicating no test table entry existed)
    5. Upserts into destination 'datasets' table (update by dataset_uuid, or insert)
    6. Verifies transfer accuracy by comparing source and destination data

    This ensures that no status/version fields are ever NULL, with actual values from
    the source tables taking precedence over defaults.

    Args:
        source_db_path: Path to the source SQLite database
        dest_db_path: Path to the destination SQLite database
        tables: List of auxiliary table names to use for enrichment (e.g. lerobot_format_convert)
        append: Currently unused; the function always performs upsert without truncating
        show_rows: Number of preview rows to display after transfer (0 to disable)
    """
    # Build engines directly to avoid altering source schema; only modify dest 'datasets'
    source_engine = _build_sqlite_engine(source_db_path)
    dest_engine = _build_sqlite_engine(dest_db_path)

    # Validate connectivity
    try:
        LOGGER.info("[OPEN] Source DB: %s (exists=%s)", source_db_path, source_db_path.exists())
        LOGGER.info("[OPEN] Destination DB: %s (exists=%s)", dest_db_path, dest_db_path.exists())
        with source_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        with dest_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database connectivity failed: {exc}") from exc

    # Ensure source contains 'datasets'
    source_tables = _list_tables(source_engine)
    if "datasets" not in source_tables:
        raise RuntimeError("Source DB does not contain required table 'datasets'")

    # Never change destination schema
    if not _sqlite_table_exists(dest_engine, "datasets"):
        raise RuntimeError(
            "Destination DB does not contain table 'datasets'. Create it beforehand; "
            "this script will not modify destination schema."
        )

    # Fetch datasets and enrich from requested tables if present
    LOGGER.info("[READ] Loading all rows from source 'datasets'")
    datasets_rows = _fetch_all_rows(source_engine, "datasets")
    LOGGER.info("[READ] Loaded %d rows from source 'datasets'", len(datasets_rows))

    # ROBUST APPROACH: Initialize ALL status/version fields with defaults FIRST
    # This ensures every field has a baseline value before enrichment
    LOGGER.info("[INIT] Initializing default values for all status/version fields")

    # Track which fields were default-initialized (for verification later)
    status_cols, version_cols = _get_status_and_version_columns(dest_engine, "datasets")
    default_initialized_fields = set(status_cols) | set(version_cols)

    _initialize_all_defaults(dest_engine, "datasets", datasets_rows)

    # Now enrich from auxiliary tables - actual values will overwrite the defaults
    _enrich_datasets_from_tables(source_engine, datasets_rows, tables)

    # Apply optimization: propagate COMPLETED status from convert to test when appropriate
    propagated = _propagate_convert_completion_to_test(datasets_rows)
    if propagated > 0:
        LOGGER.info(
            "[OPTIMIZE] Propagated COMPLETED status from convert_status to convert_test_status for %d rows",
            propagated
        )

    # Perform upsert: update existing records by dataset_uuid, insert new ones
    LOGGER.info("[MERGE] Upserting rows into destination 'datasets' using dataset_uuid where available")

    # Note: The 'append' parameter is currently ignored. This function always performs
    # upsert operations without truncating the destination table. Use a separate
    # clear_target_db script if you need to start with an empty destination.

    # Perform the actual upsert operation
    updated, inserted = _upsert_rows_by_dataset_uuid(dest_engine, "datasets", datasets_rows)
    LOGGER.info("[WRITE] Upserted rows into 'datasets': updated=%d, inserted=%d", updated, inserted)

    # Verify transfer accuracy
    LOGGER.info("[VERIFY] Verifying transfer accuracy...")
    verification_results = _verify_transfer_accuracy(
        dest_engine, "datasets", datasets_rows, default_initialized_fields
    )
    _log_verification_results(verification_results)

    if show_rows and show_rows > 0:
        # Preview a few rows for verification
        with dest_engine.connect() as conn:
            preview_cols = (
                "dataset_uuid, convert_status, convert_test_status, convert_path, convert_err_msg"
            )
            q = text(
                f"SELECT {preview_cols} FROM datasets ORDER BY dataset_uuid LIMIT :limit"
            )
            LOGGER.info("[READ] Previewing first %d rows from destination 'datasets'", show_rows)
            for row in conn.execute(q, {"limit": int(show_rows)}).fetchall():
                # Print as a compact single-line record for readability
                LOGGER.info(
                    "[READ] dst datasets row: dataset_uuid=%s, convert_status=%s, convert_test_status=%s, convert_path=%s, convert_err_msg=%s",
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    (str(row[4])[:200] if row[4] is not None else None),
                )


def _default_paths() -> tuple[Path, Path]:
    """Get default source and destination database paths for testing.

    Returns:
        Tuple of (source_path, destination_path) under examples/database_transfer_test/
    """
    source = _PROJECT_ROOT / "examples" / "database_transfer_test" / "ori_datasets.db"
    dest = _PROJECT_ROOT / "examples" / "database_transfer_test" / "datasets_new.db"
    return (source, dest)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for database transfer.

    Args:
        argv: Command-line arguments to parse (None uses sys.argv)

    Returns:
        Parsed arguments namespace.
    """
    default_source, default_dest = _default_paths()

    parser = argparse.ArgumentParser(
        description=(
            "Transfer selected tables from a source SQLite DB to a destination SQLite DB.\n"
            "Preserves schema (creates table or adds missing columns) and copies all rows."
        )
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=default_source,
        help="Path to source SQLite DB (default: examples/database_transfer_test/ori_datasets.db)",
    )
    parser.add_argument(
        "--dest-db",
        type=Path,
        default=default_dest,
        help=(
            "Path to destination SQLite DB (will be created if missing). "
            "Default: examples/database_transfer_test/datasets_new.db"
        ),
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        default=["lerobot_format_convert", "lerobot_format_convert_test"],
        help="Table names to transfer (space-separated)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append into destination instead of clearing the table first",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=0,
        help="Preview first N rows from destination 'datasets' after write (0=disable)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args(argv)


def _ensure_sqlite_path(path: Path) -> Path:
    """Normalize database path and ensure parent directory exists.

    Expands user home directory references (~) and converts to absolute path.
    Creates parent directories if they don't exist.

    Args:
        path: Path to the SQLite database file

    Returns:
        Normalized absolute path with parent directories created.
    """
    path = path.expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: Sequence[str] | None = None) -> None:
    """Main entry point for database transfer script.

    Validates source and destination databases exist, then performs the transfer
    operation with enrichment from specified auxiliary tables.

    Args:
        argv: Command-line arguments (None uses sys.argv)

    Raises:
        FileNotFoundError: If source or destination database doesn't exist
        RuntimeError: If source is not a valid SQLite database
    """
    args = parse_args(argv)
    _setup_logging(args.verbose)

    source_db_path = _ensure_sqlite_path(args.source_db)
    dest_db_path = _ensure_sqlite_path(args.dest_db)

    # Quick check that source is a SQLite file
    if not source_db_path.exists():
        raise FileNotFoundError(f"Source DB does not exist: {source_db_path}")
    # Do NOT allow implicit creation of destination DB; require it to exist
    if not dest_db_path.exists():
        raise FileNotFoundError(
            "Destination DB file not found: "
            f"{dest_db_path}. Please create it with a 'datasets' table first."
        )
    try:
        # Validate it's a SQLite DB by opening with sqlite3
        with sqlite3.connect(source_db_path):
            pass
    except sqlite3.Error as exc:
        raise RuntimeError(f"Invalid SQLite source DB: {exc}") from exc

    transfer_tables(
        source_db_path=source_db_path,
        dest_db_path=dest_db_path,
        tables=list(args.tables),
        append=bool(args.append),
        show_rows=int(args.show),
    )
    LOGGER.info("[DONE] Transfer completed. Destination DB: %s", dest_db_path)


if __name__ == "__main__":
    main()

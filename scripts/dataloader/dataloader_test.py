"""
Dataloader Test CLI - validates LeRobot datasets with local/server/client modes.

================================================================================
BASIC USAGE
================================================================================

LOCAL MODE (Single Machine Testing):
    # Test all datasets in default database
    python scripts/dataloader/dataloader_test.py --local

    # Test with custom database
    python scripts/dataloader/dataloader_test.py --local --db /path/to/your.db

    # Test with custom symlink target directory
    python scripts/dataloader/dataloader_test.py --local -t /tmp/test_symlinks

    # Test with absolute symlinks and skip missing files
    python scripts/dataloader/dataloader_test.py --local --absolute --skip-missing

SERVER MODE (Distribute Tasks):
    # Start server (binds to all interfaces, uses default database)
    python scripts/dataloader/dataloader_test.py --server

    # Start server with custom database
    python scripts/dataloader/dataloader_test.py --server --db /path/to/your.db

    # Start server on specific port
    python scripts/dataloader/dataloader_test.py --server --port 9000

    # Start server with debug logging
    python scripts/dataloader/dataloader_test.py --server --log-level DEBUG

CLIENT MODE (Connect and Process):
    # Connect to local server
    python scripts/dataloader/dataloader_test.py --client

    # Connect to remote server by IP
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100

    # Connect to remote server with custom port
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100 --port 9000

    # Connect with custom heartbeat interval
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100 --heartbeat-interval 20.0

DISTRIBUTED WORKFLOW (Server + Multiple Clients):
    # On Server Machine (192.168.1.100)
    python scripts/dataloader/dataloader_test.py --server --host 0.0.0.0 --db /path/to/datasets.db

    # On Worker Machine 1
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100

    # On Worker Machine 2
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100

    # On Worker Machine N...
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100

================================================================================
MODES
================================================================================
    --local    Run locally with symlink creation and dataloader validation
    --server   Start WebSocket server to distribute tasks
    --client   Connect to server and process tasks

COMMON OPTIONS:
    --db PATH           Database file (default: examples/dataloader_test/datasets_new.db)
    --host HOST         Server IP (server: bind address, client: connect address)
    --port PORT         Port number (default: 8771)
    --log-level LEVEL   Logging verbosity (default: INFO)

DATABASE REQUIREMENTS:
    Records must have:
    - data_merge_status = COMPLETED
    - convert_status = COMPLETED
    - convert_path populated and valid

    ⚠️ WARNING: Records with NULL data_loader_detection_status are ILLEGAL but
               will be treated as PENDING for robustness (with warnings logged)

For detailed usage, examples, and troubleshooting guide, see:
    scripts/dataloader/DATALOADER_TEST_USAGE.md
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import func

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.dataloader.dataloader import (
    DataloaderDbClient,
    DataloaderDbServer,
    _run_dataloader_detection,
)
from robocoin_dataset.dataloader.make_data_sym_links import (
    create_lerobot_symlink_structure,
)
from robocoin_dataset.utils.logger import setup_logger

DEFAULT_DB = Path("examples/dataloader_test/datasets_new.db").absolute()


def _find_first_dataset_with_convert_path(db: DatasetDatabase) -> tuple[str, Path] | None:
    """Find first dataset with valid convert_path.

    STRICT REQUIREMENTS:
      - data_merge_status must be COMPLETED
      - convert_status must be COMPLETED
      - convert_path must be non-NULL and exist as directory
    """
    with db.with_session() as session:
        row = (
            session.query(DatasetDB.dataset_uuid, DatasetDB.convert_path)
            .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)
            .filter(DatasetDB.convert_status == TaskStatus.COMPLETED)
            .filter(DatasetDB.convert_path != None)  # noqa: E711
            .first()
        )
        if not row:
            return None
        ds_uuid, convert_path = row
        src = Path(convert_path)
        if not (src.exists() and src.is_dir()):
            return None
        return ds_uuid, src


def _find_all_datasets_with_convert_path(db: DatasetDatabase) -> list[tuple[str, Path]]:
    """Find all datasets with valid convert_path.

    STRICT REQUIREMENTS:
      - data_merge_status must be COMPLETED
      - convert_status must be COMPLETED
      - convert_path must be non-NULL and exist as directory
    """
    with db.with_session() as session:
        rows = (
            session.query(DatasetDB.dataset_uuid, DatasetDB.convert_path)
            .filter(DatasetDB.data_merge_status == TaskStatus.COMPLETED)
            .filter(DatasetDB.convert_status == TaskStatus.COMPLETED)
            .filter(DatasetDB.convert_path != None)  # noqa: E711
            .all()
        )
        result = []
        for ds_uuid, convert_path in rows:
            src = Path(convert_path)
            if src.exists() and src.is_dir():
                result.append((ds_uuid, src))
        return result


def _update_detection_status(db: DatasetDatabase, ds_uuid: str, ok: bool, err_msg: str | None) -> None:
    with db.with_session() as session:
        values = {
            DatasetDB.data_loader_detection_status: TaskStatus.COMPLETED if ok else TaskStatus.FAILED,
            DatasetDB.data_loader_detection_version: func.coalesce(DatasetDB.data_loader_detection_version, 0)
            + 1,
            # set PS to current data_merge_version as requested
            DatasetDB.data_loader_detection_version_ps: DatasetDB.data_merge_version,
        }
        if not ok and err_msg:
            values[DatasetDB.data_loader_detection_err_msg] = err_msg
        session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).update(values, synchronize_session=False)
        session.commit()


def run_local(
    db_file: Path,
    target_dir: Path | None,
    absolute_symlinks: bool,
    skip_missing: bool,
    logger: logging.Logger,
) -> int:
    db = DatasetDatabase(db_file)
    datasets = _find_all_datasets_with_convert_path(db)
    if not datasets:
        print("No dataset with a valid convert_path found in DB", file=sys.stderr)
        return 2

    logger.info(f"Found {len(datasets)} dataset(s) to process")

    succeeded = []
    failed = []

    for idx, (ds_uuid, source_dir) in enumerate(datasets, 1):
        logger.info(f"Processing dataset {idx}/{len(datasets)}: {ds_uuid}")

        tgt = target_dir
        if tgt is None:
            tgt = source_dir.parent / f"{source_dir.name}_symlink"

        # Try symlink creation
        try:
            create_lerobot_symlink_structure(
                source_dir=source_dir,
                target_dir=tgt,
                relative=not absolute_symlinks,
                skip_missing=skip_missing,
            )
        except Exception as e:
            err_msg = f"Symlink creation failed: {e}"
            logger.error(f"Dataset {ds_uuid}: {err_msg}")
            print(f"\n⚠️  WARNING: Dataset {ds_uuid} FAILED dataloader test", file=sys.stderr)
            print(f"    Reason: {err_msg}", file=sys.stderr)
            print(f"    Source: {source_dir}\n", file=sys.stderr)
            _update_detection_status(db, ds_uuid, ok=False, err_msg=err_msg)
            failed.append((ds_uuid, err_msg))
            continue  # Go to next dataset

        # Try dataloader detection
        ok = True
        err: str | None = None
        try:
            _run_dataloader_detection(tgt)
            logger.info(f"Dataset {ds_uuid}: dataloader detection completed")
        except Exception as e:
            ok = False
            err = str(e)
            logger.error(f"Dataset {ds_uuid}: dataloader detection failed: {err}")
            print(f"\n⚠️  WARNING: Dataset {ds_uuid} FAILED dataloader test", file=sys.stderr)
            print(f"    Reason: Dataloader detection failed - {err}", file=sys.stderr)
            print(f"    Source: {source_dir}", file=sys.stderr)
            print(f"    Symlink: {tgt}\n", file=sys.stderr)

        # Update status
        _update_detection_status(db, ds_uuid, ok=ok, err_msg=err)

        if ok:
            succeeded.append(ds_uuid)
        else:
            failed.append((ds_uuid, err))

    # Summary
    logger.info("=" * 60)
    logger.info(f"Processing complete: {len(succeeded)} succeeded, {len(failed)} failed")

    print("\n" + "=" * 70, file=sys.stderr)
    print("📊 DATALOADER TEST SUMMARY", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"✅ Succeeded: {len(succeeded)}", file=sys.stderr)
    print(f"❌ Failed: {len(failed)}", file=sys.stderr)

    if succeeded:
        logger.info(f"Succeeded: {succeeded}")
        print("\n✅ Successful datasets:", file=sys.stderr)
        for ds_uuid in succeeded:
            print(f"   - {ds_uuid}", file=sys.stderr)

    if failed:
        logger.info("Failed datasets:")
        for ds_uuid, err_msg in failed:
            logger.info(f"  - {ds_uuid}: {err_msg}")
        print("\n❌ Failed datasets with error details:", file=sys.stderr)
        for ds_uuid, err_msg in failed:
            print(f"   - {ds_uuid}", file=sys.stderr)
            print(f"     Error: {err_msg}", file=sys.stderr)

    print("=" * 70 + "\n", file=sys.stderr)

    return 0 if not failed else 1


async def run_server_async(
    db_file: Path, host: str, port: int, heartbeat_interval: float, timeout: float, logger: logging.Logger
) -> int:
    server = DataloaderDbServer(
        db_file_path=db_file,
        host=host,
        port=port,
        heartbeat_interval=heartbeat_interval,
        timeout=timeout,
        logger=logger,
    )
    await server.start()
    return 0


async def run_client_async(server_uri: str, heartbeat_interval: float, logger: logging.Logger) -> int:
    client = DataloaderDbClient(server_uri=server_uri, heartbeat_interval=heartbeat_interval, logger=logger)
    await client.run_until_no_task()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merged CLI: local symlink test, server, client",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to SQLite database (default: examples/dataloader_test/datasets_new.db)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    # execution mode (choose one)
    parser.add_argument("--local", action="store_true", help="Run locally: symlink + load + DB update")
    parser.add_argument("--server", action="store_true", help="Run dataloader detection server")
    parser.add_argument("--client", action="store_true", help="Run dataloader detection client")
    parser.add_argument("--cliet", action="store_true", help="Alias of --client")

    # network args (context-dependent: server bind address OR client connect address)
    parser.add_argument("--host", type=str, default=None, help="Host address (Server: bind to; Client: connect to)")
    parser.add_argument("--port", type=int, default=8771, help="Port number (default: 8771)")
    parser.add_argument("--heartbeat-interval", type=float, default=30.0, help="Heartbeat interval in seconds")
    parser.add_argument("--timeout", type=float, default=15.0, help="Server: heartbeat timeout in seconds")
    parser.add_argument("--log-dir", type=Path, default=Path(""), help="Log directory")

    # local symlink args
    parser.add_argument("-t", "--target", type=Path, default=None, help="Target directory for symlinked dataset")
    parser.add_argument("--absolute", action="store_true", help="Create absolute symlinks (default: relative)")
    parser.add_argument("--skip-missing", action="store_true", help="Skip missing source files")

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger = setup_logger(
        name="dataloader merged cli",
        log_dir=Path(args.log_dir) if hasattr(args, "log_dir") else Path(""),
        level=getattr(logging, args.log_level, logging.INFO),
    )

    db_file = args.db.expanduser().absolute()

    # default to --local if no mode specified
    run_local_mode = bool(args.local or (not args.server and not (args.client or args.cliet)))

    if run_local_mode:
        return run_local(
            db_file=db_file,
            target_dir=(args.target.expanduser().absolute() if args.target else None),
            absolute_symlinks=bool(args.absolute),
            skip_missing=bool(args.skip_missing),
            logger=logger,
        )

    if args.server:
        # Server mode: --host defaults to 0.0.0.0 (bind to all interfaces)
        host = args.host if args.host is not None else "0.0.0.0"
        return asyncio.run(
            run_server_async(
                db_file=db_file,
                host=host,
                port=args.port,
                heartbeat_interval=args.heartbeat_interval,
                timeout=args.timeout,
                logger=logger,
            )
        )

    if args.client or args.cliet:
        # Client mode: --host defaults to localhost (connect to local server)
        host = args.host if args.host is not None else "localhost"
        server_uri = f"ws://{host}:{args.port}"
        return asyncio.run(
            run_client_async(
                server_uri=server_uri,
                heartbeat_interval=args.heartbeat_interval if hasattr(args, "heartbeat_interval") else 10.0,
                logger=logger,
            )
        )

    print("No mode selected", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

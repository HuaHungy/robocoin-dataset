"""
Dataloader Test CLI - validates LeRobot datasets with local/server/client modes.

================================================================================
BASIC USAGE
================================================================================

LOCAL MODE (Single Machine Testing):
    # Test all datasets in default database (tests ALL episodes by default)
    python scripts/dataloader/dataloader_test.py --local

    # Test with custom database
    python scripts/dataloader/dataloader_test.py --local --db /path/to/your.db

    # Test only specific episodes (e.g., episode 0 only)
    python scripts/dataloader/dataloader_test.py --local --episodes 0

    # Test episode range (e.g., episodes 0-5)
    python scripts/dataloader/dataloader_test.py --local --episodes 0-5

    # Test specific episodes (e.g., 0, 1, and 5)
    python scripts/dataloader/dataloader_test.py --local --episodes "0,1,5"

    # Test with strict mode (fail immediately on first error)
    python scripts/dataloader/dataloader_test.py --local --strict

    # Test with custom batch size and workers
    python scripts/dataloader/dataloader_test.py --local --batch-size 64 --num-workers 4

    # Test with custom symlink target directory
    python scripts/dataloader/dataloader_test.py --local -t /tmp/test_symlinks

    # Test with absolute symlinks and skip missing files during symlink creation
    python scripts/dataloader/dataloader_test.py --local --absolute --symlink-skip-missing

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

MULTI-CLIENT MODE (Spawn Multiple Processes on Single Machine):
    # Spawn 12 client processes on one machine
    python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100 --num-clients 12

    # Spawn 4 local processes to parallelize local testing
    python scripts/dataloader/dataloader_test.py --local --num-clients 4

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
    --db PATH               Database file (default: examples/dataloader_test/datasets_new.db)
    --host HOST             Server IP (server: bind address, client: connect address)
    --port PORT             Port number (default: 8771)
    --log-level LEVEL       Logging verbosity (default: INFO)
    --num-clients N         Number of parallel processes (default: 1, max: 32)

VALIDATION OPTIONS:
    --episodes SPEC         Episodes to test: "all" (default), "0", "0,1,2", "0-5"
    --strict                Fail immediately on first error (default: False)
    --batch-size N          Batch size for dataloader (default: 32)
    --num-workers N         Number of dataloader workers (default: 0)

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
import multiprocessing as mp
import sys
from pathlib import Path

from sqlalchemy import func

from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import DatasetDB, TaskStatus
from robocoin_dataset.dataloader.dataloader import (
    DataloaderDbServer,
    _run_dataloader_detection,
    run_client_async,
    run_multi_client,
    run_multi_local,
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


def _update_detection_status(
    db: DatasetDatabase, ds_uuid: str, ok: bool, err_msg: str | None
) -> None:
    with db.with_session() as session:
        values = {
            DatasetDB.data_loader_detection_status: TaskStatus.COMPLETED
            if ok
            else TaskStatus.FAILED,
            DatasetDB.data_loader_detection_version: func.coalesce(
                DatasetDB.data_loader_detection_version, 0
            )
            + 1,
            # set PS to current data_merge_version as requested
            DatasetDB.data_loader_detection_version_ps: DatasetDB.data_merge_version,
        }
        if not ok and err_msg:
            values[DatasetDB.data_loader_detection_err_msg] = err_msg
        session.query(DatasetDB).filter(DatasetDB.dataset_uuid == ds_uuid).update(
            values, synchronize_session=False
        )
        session.commit()


def run_local(
    db_file: Path,
    target_dir: Path | None,
    absolute_symlinks: bool,
    skip_missing: bool,
    episodes: str,
    strict_mode: bool,
    batch_size: int,
    num_workers: int,
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

        # Try comprehensive dataloader detection with user-specified parameters
        result = _run_dataloader_detection(
            tgt,
            episode_indices=episodes,
            strict_mode=strict_mode,
            batch_size=batch_size,
            num_workers=num_workers,
        )

        ok = result["success"]
        err = result.get("error_summary")

        if ok:
            logger.info(
                f"Dataset {ds_uuid}: validation completed - "
                f"{result['total_frames_validated']} frames in {len(result['episodes_tested'])} episodes"
            )
            succeeded.append(ds_uuid)
        else:
            logger.error(f"Dataset {ds_uuid}: validation failed: {err}")
            print(f"\n⚠️  WARNING: Dataset {ds_uuid} FAILED dataloader test", file=sys.stderr)
            print(f"    Reason: {err}", file=sys.stderr)
            print(f"    Episodes tested: {len(result['episodes_tested'])}", file=sys.stderr)
            print(f"    Episodes failed: {len(result['episodes_failed'])}", file=sys.stderr)
            print(f"    Source: {source_dir}", file=sys.stderr)
            print(f"    Symlink: {tgt}\n", file=sys.stderr)
            failed.append((ds_uuid, err))

        # Update status
        _update_detection_status(db, ds_uuid, ok=ok, err_msg=err)

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
    db_file: Path,
    host: str,
    port: int,
    heartbeat_interval: float,
    timeout: float,
    logger: logging.Logger,
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
    parser.add_argument(
        "--local", action="store_true", help="Run locally: symlink + load + DB update"
    )
    parser.add_argument("--server", action="store_true", help="Run dataloader detection server")
    parser.add_argument("--client", action="store_true", help="Run dataloader detection client")
    parser.add_argument("--cliet", action="store_true", help="Alias of --client")

    # network args (context-dependent: server bind address OR client connect address)
    parser.add_argument(
        "--host", type=str, default=None, help="Host address (Server: bind to; Client: connect to)"
    )
    parser.add_argument("--port", type=int, default=8771, help="Port number (default: 8771)")
    parser.add_argument(
        "--heartbeat-interval", type=float, default=30.0, help="Heartbeat interval in seconds"
    )
    parser.add_argument(
        "--timeout", type=float, default=15.0, help="Server: heartbeat timeout in seconds"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("./logs/dataloader"),
        help="Log directory (default: /logs/dataloader)",
    )

    # local symlink args
    parser.add_argument(
        "-t", "--target", type=Path, default=None, help="Target directory for symlinked dataset"
    )
    parser.add_argument(
        "--absolute", action="store_true", help="Create absolute symlinks (default: relative)"
    )
    parser.add_argument(
        "--symlink-skip-missing",
        action="store_true",
        help="Skip missing source files during symlink creation",
    )

    # dataloader validation args
    parser.add_argument(
        "--episodes",
        type=str,
        default="all",
        help='Episodes to test: "all" (default), "0", "0,1,2", or "0-5"',
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: fail immediately on first error (default: False, collect all errors)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for dataloader (default: 32)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Number of dataloader workers (default: 0)",
    )

    # multi-process args
    parser.add_argument(
        "--num-clients",
        type=int,
        default=1,
        help="Number of concurrent client/local processes to spawn (default: 1, max: 32)",
    )

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger = setup_logger(
        name="dataloader merged cli",
        log_dir=Path(args.log_dir) if hasattr(args, "log_dir") else Path("/logs/dataloader"),
        level=getattr(logging, args.log_level, logging.INFO),
    )

    # Validation: reject --num-clients with --server
    num_clients = getattr(args, "num_clients", 1)
    if args.server and num_clients > 1:
        print("ERROR: --num-clients is not supported with --server mode", file=sys.stderr)
        print("       Use --num-clients with --client or --local mode only", file=sys.stderr)
        return 2

    # Apply max limit to num_clients
    if num_clients > 32:
        print(f"WARNING: --num-clients={num_clients} exceeds maximum limit of 32", file=sys.stderr)
        print("         Capping to 32 clients", file=sys.stderr)
        num_clients = 32
    elif num_clients < 1:
        print(f"WARNING: --num-clients={num_clients} is invalid", file=sys.stderr)
        print("         Using minimum of 1 client", file=sys.stderr)
        num_clients = 1

    db_file = args.db.expanduser().absolute()

    # Validate database exists before spawning processes (except for server mode)
    if not args.server:
        if not db_file.exists():
            print(f"ERROR: Database file not found: {db_file}", file=sys.stderr)
            return 2
        if not db_file.is_file():
            print(f"ERROR: Database path is not a file: {db_file}", file=sys.stderr)
            return 2

    # default to --local if no mode specified
    run_local_mode = bool(args.local or (not args.server and not (args.client or args.cliet)))

    if run_local_mode:
        # Multi-local mode: spawn multiple processes
        if num_clients > 1:
            return run_multi_local(
                db_file=db_file,
                num_processes=num_clients,
                target_dir=(args.target.expanduser().absolute() if args.target else None),
                absolute_symlinks=bool(args.absolute),
                skip_missing=bool(args.symlink_skip_missing),
                log_dir=args.log_dir,
                log_level=args.log_level,
            )

        # Single-process local mode (original behavior)
        return run_local(
            db_file=db_file,
            target_dir=(args.target.expanduser().absolute() if args.target else None),
            absolute_symlinks=bool(args.absolute),
            skip_missing=bool(args.symlink_skip_missing),
            episodes=args.episodes,
            strict_mode=bool(args.strict),
            batch_size=args.batch_size,
            num_workers=args.num_workers,
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

        # Multi-client mode: spawn multiple processes
        if num_clients > 1:
            return run_multi_client(
                server_uri=server_uri,
                num_clients=num_clients,
                heartbeat_interval=args.heartbeat_interval,
                log_dir=args.log_dir,
                log_level=args.log_level,
            )

        # Single client mode (original behavior)
        stats = asyncio.run(
            run_client_async(
                server_uri=server_uri,
                heartbeat_interval=args.heartbeat_interval
                if hasattr(args, "heartbeat_interval")
                else 10.0,
                logger=logger,
            )
        )
        # Return 0 if no tasks failed, 1 otherwise
        return 0 if stats["tasks_failed"] == 0 else 1

    print("No mode selected", file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Set multiprocessing start method for cross-platform compatibility
    mp.set_start_method("spawn", force=True)
    raise SystemExit(main(sys.argv[1:]))

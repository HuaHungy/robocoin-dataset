"""
Dataloader Test CLI - validates LeRobot datasets with local/server/client modes.

"""

import argparse
import asyncio
import logging
import multiprocessing as mp
import sys
from pathlib import Path

from robocoin_dataset.dataloader.dataloader import (
    DataloaderDbServer,
    run_client_async,
    run_local_batch_detection,
    run_multi_client,
)
from robocoin_dataset.utils.logger import setup_logger

DEFAULT_DB = Path("examples/dataloader_test/datasets_new.db").absolute()


def run_local(
    db_file: Path,
    target_dir: Path | None,
    absolute_hardlinks: bool,
    skip_missing: bool,
    episodes: str,
    comprehensive: bool,
    sample_ratio: float,
    strict_mode: bool,
    batch_size: int,
    num_workers: int,
    logger: logging.Logger,
) -> int:
    """Local mode: thin wrapper that calls core logic in dataloader.py"""

    result = run_local_batch_detection(
        db_file=db_file,
        episodes=episodes,
        comprehensive=comprehensive,
        sample_ratio=sample_ratio,
        strict_mode=strict_mode,
        batch_size=batch_size,
        num_workers=num_workers,
        create_hardlinks=True,
        hardlink_target_dir=target_dir,
        hardlink_relative=not absolute_hardlinks,
        hardlink_skip_missing=skip_missing,
        logger=logger,
    )

    # Check if no tasks were processed
    if result["datasets_processed"] == 0:
        print("\n" + "=" * 70, file=sys.stderr)
        print("ℹ️  NO TASKS TO PROCESS", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print("\nAll datasets are either:", file=sys.stderr)
        print("  • Already validated and up-to-date (data_loader_detection_status = COMPLETED", file=sys.stderr)
        print("    AND data_loader_detection_version_ps == data_merge_version)", file=sys.stderr)
        print("  • Not ready for validation (data_merge_status or convert_status not COMPLETED)", file=sys.stderr)
        print("\nIf you expected tasks to process, check:", file=sys.stderr)
        print("  1. Database has datasets with data_merge_status = COMPLETED", file=sys.stderr)
        print("  2. Database has datasets with convert_status = COMPLETED", file=sys.stderr)
        print("  3. Datasets have valid convert_path", file=sys.stderr)
        print("  4. data_loader_detection_status is NULL, PENDING, or outdated COMPLETED", file=sys.stderr)
        print("=" * 70 + "\n", file=sys.stderr)
        return 0

    # Print summary
    print("\n" + "=" * 70, file=sys.stderr)
    print("📊 DATALOADER TEST SUMMARY", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"📦 Datasets processed: {result['datasets_processed']}", file=sys.stderr)
    print(f"✅ Succeeded: {len(result['succeeded'])}", file=sys.stderr)
    print(f"❌ Failed: {len(result['failed'])}", file=sys.stderr)

    if result["succeeded"]:
        print("\n✅ Successful datasets:", file=sys.stderr)
        for ds_uuid in result["succeeded"]:
            print(f"   - {ds_uuid}", file=sys.stderr)

    if result["failed"]:
        print("\n❌ Failed datasets:", file=sys.stderr)
        for ds_uuid, err_msg in result["failed"]:
            print(f"   - {ds_uuid}", file=sys.stderr)
            print(f"     Error: {err_msg}", file=sys.stderr)

    print("=" * 70 + "\n", file=sys.stderr)

    return 0 if not result["failed"] else 1


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merged CLI: local hardlink test, server, client",
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
    parser.add_argument("--local", action="store_true", help="Run locally: hardlink + load + DB update")
    parser.add_argument("--server", action="store_true", help="Run dataloader detection server")
    parser.add_argument("--client", action="store_true", help="Run dataloader detection client")
    parser.add_argument("--cliet", action="store_true", help="Alias of --client")

    # network args (context-dependent: server bind address OR client connect address)
    parser.add_argument("--host", type=str, default=None, help="Host address (Server: bind to; Client: connect to)")
    parser.add_argument("--port", type=int, default=8771, help="Port number (default: 8771)")
    parser.add_argument("--heartbeat-interval", type=float, default=30.0, help="Heartbeat interval in seconds")
    parser.add_argument("--timeout", type=float, default=15.0, help="Server: heartbeat timeout in seconds")
    parser.add_argument("--log-dir", type=Path, default=Path("logs/dataloader"), help="Log directory relative to current directory (default: logs/dataloader)")

    # local hardlink args
    parser.add_argument("-t", "--target", type=Path, default=None, help="Target directory for hardlinked dataset")
    parser.add_argument("--absolute", action="store_true", help="Create absolute hardlinks (default: relative)")
    parser.add_argument("--hardlink-skip-missing", action="store_true", help="Skip missing source files during hardlink creation")

    # dataloader validation args
    parser.add_argument(
        "--episodes",
        type=str,
        default="all",
        help='Episodes to test: "all" (default), "0", "0,1,2", or "0-5"',
    )
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Use comprehensive detection (test all frames with validation). Default: fast detection with 10%% sampling",
    )
    parser.add_argument(
        "--sample-ratio",
        type=float,
        default=0.1,
        help="Sample ratio for fast detection (0.0-1.0, default: 0.1 = 10%%). Ignored if --comprehensive is used",
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
        help="Number of concurrent client processes to spawn (default: 1, max: 32, only supported with --client mode)",
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
        log_dir=Path(args.log_dir) if hasattr(args, "log_dir") else Path("logs/dataloader"),
        level=getattr(logging, args.log_level, logging.INFO),
    )

    # Validation: reject --num-clients with --server or --local
    num_clients = getattr(args, 'num_clients', 1)
    if args.server and num_clients > 1:
        print("ERROR: --num-clients is not supported with --server mode", file=sys.stderr)
        print("       Use --num-clients with --client mode only", file=sys.stderr)
        return 2

    if args.local and num_clients > 1:
        print("ERROR: --num-clients is not supported with --local mode", file=sys.stderr)
        print("       Multi-local mode has been abandoned", file=sys.stderr)
        print("       Use --num-clients with --client mode only", file=sys.stderr)
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
        # Single-process local mode
        return run_local(
            db_file=db_file,
            target_dir=(args.target.expanduser().absolute() if args.target else None),
            absolute_hardlinks=bool(args.absolute),
            skip_missing=bool(args.hardlink_skip_missing),
            episodes=args.episodes,
            comprehensive=bool(args.comprehensive),
            sample_ratio=args.sample_ratio,
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
                heartbeat_interval=args.heartbeat_interval if hasattr(args, "heartbeat_interval") else 10.0,
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

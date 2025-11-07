"""Dataloader Test CLI - unified entry point for dataset validation.

Modes (default: --local):
  --local   : Process datasets locally with automatic hardlink management
  --server  : Run task distribution server
  --client  : Connect to server and process tasks (supports --num-clients)

All modes leverage functions from dataloader.py for maximum code reuse.
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


def _print_no_tasks_message() -> None:
    """Print informative message when no tasks are available."""
    print("\nℹ️  No tasks to process", file=sys.stderr)
    print("   All datasets are validated or not ready", file=sys.stderr)
    print("   Check: data_merge_status, convert_status, convert_path\n", file=sys.stderr)


def _print_result_summary(result: dict) -> None:
    """Print formatted summary of detection results."""
    total = result['datasets_processed']
    succeeded = len(result['succeeded'])
    failed = len(result['failed'])

    print(f"\n📊 Summary: {succeeded}/{total} succeeded, {failed}/{total} failed", file=sys.stderr)

    # Performance summary
    total_time = result.get('total_time_s', 0)
    total_frames = result.get('total_frames', 0)
    avg_time_per_frame = result.get('avg_time_per_frame_s', 0)

    if total_time > 0:
        print(
            f"⏱️  Performance: {total_time:.2f}s total, {total_frames} frames, "
            f"{avg_time_per_frame*1000:.1f}ms/frame avg",
            file=sys.stderr
        )

    if result["succeeded"]:
        print(f"\n✅ Succeeded ({succeeded}):", file=sys.stderr)
        for ds_uuid in result["succeeded"]:
            print(f"   {ds_uuid}", file=sys.stderr)

    if result["failed"]:
        print(f"\n❌ Failed ({failed}):", file=sys.stderr)
        for ds_uuid, err_msg in result["failed"]:
            # Truncate long error messages
            short_err = err_msg[:80] + "..." if len(err_msg) > 80 else err_msg
            print(f"   {ds_uuid}: {short_err}", file=sys.stderr)

    print(file=sys.stderr)


def run_local(
    db_file: Path,
    target_dir: Path | None,
    episodes: str,
    sample_ratio: float,
    batch_size: int,
    num_workers: int,
    logger: logging.Logger,
) -> int:
    """Local mode: process datasets with automatic hardlink management."""
    from datetime import datetime

    from robocoin_dataset.utils.logger import setup_logger

    # Create summary logger in logs/dataloader/sum/
    sum_logger = setup_logger(
        name="dataloader_summary",
        log_dir=Path("logs/dataloader/sum"),
        level=logging.INFO,
    )

    # Log execution parameters
    sum_logger.info("="*80)
    sum_logger.info(f"Execution started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sum_logger.info("CLI Parameters:")
    sum_logger.info(f"  --db={db_file}")
    sum_logger.info(f"  --target={target_dir}")
    sum_logger.info(f"  --episodes={episodes}")
    sum_logger.info(f"  --sample-ratio={sample_ratio}")
    sum_logger.info(f"  --batch-size={batch_size}")
    sum_logger.info(f"  --num-workers={num_workers}")
    sum_logger.info("="*80)

    result = run_local_batch_detection(
        db_file=db_file,
        episodes=episodes,
        sample_ratio=sample_ratio,
        batch_size=batch_size,
        num_workers=num_workers,
        hardlink_target_dir=target_dir,
        logger=logger,
        summary_logger=sum_logger,
    )

    if result["datasets_processed"] == 0:
        _print_no_tasks_message()
        sum_logger.info("No tasks processed")
        return 0

    _print_result_summary(result)

    # Write summary to summary logger
    sum_logger.info("-"*80)
    sum_logger.info("Execution Summary:")
    sum_logger.info(f"  Total datasets: {result['datasets_processed']}")
    sum_logger.info(f"  Succeeded: {len(result['succeeded'])}")
    sum_logger.info(f"  Failed: {len(result['failed'])}")
    sum_logger.info(f"  Total time: {result.get('total_time_s', 0):.2f}s")
    sum_logger.info(f"  Total frames: {result.get('total_frames', 0)}")
    sum_logger.info(f"  Avg time/frame: {result.get('avg_time_per_frame_s', 0)*1000:.1f}ms")
    sum_logger.info("="*80 + "\n")

    return 0 if not result["failed"] else 1


async def run_server_async(
    db_file: Path,
    host: str,
    port: int,
    heartbeat_interval: float,
    timeout: float,
    logger: logging.Logger,
    episodes: str = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
) -> int:
    """Server mode: start task distribution server."""
    from datetime import datetime

    from robocoin_dataset.utils.logger import setup_logger

    # Create summary logger
    sum_logger = setup_logger(
        name="dataloader_summary",
        log_dir=Path("logs/dataloader/sum"),
        level=logging.INFO,
    )

    # Log execution parameters
    sum_logger.info("="*80)
    sum_logger.info(f"Server started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sum_logger.info("Server Parameters:")
    sum_logger.info(f"  --db={db_file}")
    sum_logger.info(f"  --host={host}")
    sum_logger.info(f"  --port={port}")
    sum_logger.info(f"  --episodes={episodes}")
    sum_logger.info(f"  --sample-ratio={sample_ratio}")
    sum_logger.info(f"  --batch-size={batch_size}")
    sum_logger.info(f"  --num-workers={num_workers}")
    sum_logger.info(f"  --heartbeat-interval={heartbeat_interval}")
    sum_logger.info(f"  --timeout={timeout}")
    sum_logger.info("="*80)

    server = DataloaderDbServer(
        db_file_path=db_file,
        host=host,
        port=port,
        heartbeat_interval=heartbeat_interval,
        timeout=timeout,
        logger=logger,
        episodes=episodes,
        sample_ratio=sample_ratio,
        batch_size=batch_size,
        num_workers=num_workers,
        summary_logger=sum_logger,
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
        default=None,
        help="Path to SQLite database (required for --server and --local modes, not needed for --client)",
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
    parser.add_argument("-t", "--target", type=Path, default=None, help="Target directory for hardlinked dataset (default: {source}_hardlink)")

    # dataloader validation args
    parser.add_argument(
        "--episodes",
        type=str,
        default="all",
        help='Episodes to test: "all" (default), "0", "0,1,2", or "0-5"',
    )
    parser.add_argument(
        "--sample-ratio",
        type=float,
        default=1.0,
        help="Sample ratio for fast detection (0.0-1.0, default: 0.1 = 10%%)",
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


def _validate_num_clients(args: argparse.Namespace) -> int:
    """Validate and normalize num_clients argument."""
    num_clients = getattr(args, 'num_clients', 1)

    if (args.server or args.local) and num_clients > 1:
        print("❌ --num-clients only works with --client mode", file=sys.stderr)
        return 2

    if num_clients > 32:
        print(f"⚠️  Capping num_clients: {num_clients} → 32", file=sys.stderr)
        return 32
    if num_clients < 1:
        print(f"⚠️  Invalid num_clients: {num_clients} → 1", file=sys.stderr)
        return 1

    return num_clients


def _validate_database(args: argparse.Namespace) -> Path | None:
    """Validate database path for server/local modes."""
    if args.client or args.cliet:
        return None

    if args.db is None:
        print("❌ --db required for --server/--local modes", file=sys.stderr)
        raise SystemExit(2)

    db_file = args.db.expanduser().absolute()

    if not db_file.exists():
        print(f"❌ Database not found: {db_file}", file=sys.stderr)
        raise SystemExit(2)
    if not db_file.is_file():
        print(f"❌ Not a file: {db_file}", file=sys.stderr)
        raise SystemExit(2)

    return db_file


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = setup_logger(
        name="dataloader_cli",
        log_dir=Path(args.log_dir) if hasattr(args, "log_dir") else Path("logs/dataloader"),
        level=getattr(logging, args.log_level, logging.INFO),
    )

    # Validate arguments
    num_clients = _validate_num_clients(args)
    if num_clients == 2:  # Error code
        return 2

    db_file = _validate_database(args)

    # Execute based on mode (default: local)
    if args.server:
        return asyncio.run(
            run_server_async(
                db_file=db_file,
                host=args.host or "0.0.0.0",  # Bind to all interfaces
                port=args.port,
                heartbeat_interval=args.heartbeat_interval,
                timeout=args.timeout,
                logger=logger,
                episodes=args.episodes,
                sample_ratio=args.sample_ratio,
                batch_size=args.batch_size,
                num_workers=args.num_workers,
            )
        )

    if args.client or args.cliet:
        server_uri = f"ws://{args.host or 'localhost'}:{args.port}"

        if num_clients > 1:
            return run_multi_client(
                server_uri=server_uri,
                num_clients=num_clients,
                heartbeat_interval=args.heartbeat_interval,
                log_dir=args.log_dir,
                log_level=args.log_level,
            )

        # Single client
        stats = asyncio.run(
            run_client_async(
                server_uri=server_uri,
                heartbeat_interval=args.heartbeat_interval,
                logger=logger,
            )
        )
        return 0 if stats["tasks_failed"] == 0 else 1

    # Default: local mode
    return run_local(
        db_file=db_file,
        target_dir=(args.target.expanduser().absolute() if args.target else None),
        episodes=args.episodes,
        sample_ratio=args.sample_ratio,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        logger=logger,
    )


if __name__ == "__main__":
    # Set multiprocessing start method for cross-platform compatibility
    mp.set_start_method("spawn", force=True)
    raise SystemExit(main(sys.argv[1:]))

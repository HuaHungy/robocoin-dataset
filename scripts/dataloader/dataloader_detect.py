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
import statistics
import sys
from datetime import datetime
from pathlib import Path

from robocoin_dataset.dataloader.dataloader_client import (
    run_multi_clients,
    run_one_client_async,
)
from robocoin_dataset.dataloader.dataloader_local import run_local_detection
from robocoin_dataset.dataloader.dataloader_server import DataloaderDbServer
from robocoin_dataset.utils.logger import setup_logger


def _create_log_dir_name(args: argparse.Namespace) -> str:
    """Create log directory name with date and key parameters."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Determine mode
    if args.server:
        mode = "server"
    elif args.client or args.cliet:
        mode = f"client_n{getattr(args, 'num_clients', 1)}"
    else:
        mode = "local"

    # Key parameters
    parts = [timestamp, mode]

    if hasattr(args, 'num_workers') and args.num_workers > 0:
        parts.append(f"w{args.num_workers}")

    if hasattr(args, 'sample_ratio') and args.sample_ratio != 1.0:
        parts.append(f"sr{args.sample_ratio:.2f}")

    if hasattr(args, 'batch_size') and args.batch_size != 32:
        parts.append(f"bs{args.batch_size}")

    if hasattr(args, 'episodes') and args.episodes != "all":
        ep_str = args.episodes.replace(',', '_').replace('-', 'to')[:20]
        parts.append(f"ep{ep_str}")

    return "_".join(parts)


def _print_no_tasks_message(logger: logging.Logger) -> None:
    """Log informative message when no tasks are available."""
    msg = "\nℹ️  No tasks to process\n   All datasets are validated or not ready\n   Check: qced_repo_gen_status (must be COMPLETED), data_loader_detection_status (must be PENDING), and hardlink records\n"
    logger.info(msg)


def _log_detailed_episode_statistics(dataset_stats: list[dict], sum_logger: logging.Logger) -> None:
    """Log detailed episode-level statistics to summary logger.

    This provides a breakdown similar to analyze_episode_timing.py but integrated
    into the summary log during execution.
    """
    if not dataset_stats:
        return

    times_per_episode = [s['time_per_episode_sec'] for s in dataset_stats]
    total_episodes = sum(s['num_episodes'] for s in dataset_stats)
    total_frames = sum(s['total_frames'] for s in dataset_stats)
    total_time = sum(s['total_time_sec'] for s in dataset_stats)

    sum_logger.info("="*80)
    sum_logger.info("📈 EPISODE-LEVEL STATISTICS")
    sum_logger.info("="*80)

    sum_logger.info("")
    sum_logger.info("🎯 Episode Timing:")
    sum_logger.info(f"   Mean time per episode:   {statistics.mean(times_per_episode):.2f} seconds")
    sum_logger.info(f"   Median time per episode: {statistics.median(times_per_episode):.2f} seconds")
    sum_logger.info(f"   Min time per episode:    {min(times_per_episode):.2f} seconds")
    sum_logger.info(f"   Max time per episode:    {max(times_per_episode):.2f} seconds")
    if len(times_per_episode) > 1:
        sum_logger.info(f"   Std deviation:           {statistics.stdev(times_per_episode):.2f} seconds")

    sum_logger.info("")
    sum_logger.info("📊 Overall Statistics:")
    sum_logger.info(f"   Total datasets analyzed: {len(dataset_stats)}")
    sum_logger.info(f"   Total episodes:          {total_episodes}")
    sum_logger.info(f"   Total frames:            {total_frames:,}")
    sum_logger.info(f"   Total processing time:   {total_time:.2f} seconds ({total_time/60:.1f} minutes)")
    sum_logger.info(f"   Avg frames per episode:  {total_frames/total_episodes:.0f}")

    sum_logger.info("")
    sum_logger.info("="*80)
    sum_logger.info("📋 PER-DATASET BREAKDOWN")
    sum_logger.info("="*80)

    # Sort by time per episode
    sorted_stats = sorted(dataset_stats, key=lambda x: x['time_per_episode_sec'])

    sum_logger.info("")
    sum_logger.info(f"{'Dataset':<50} {'Episodes':>8} {'Sec/Ep':>8} {'Frames/Ep':>10}")
    sum_logger.info("-" * 80)
    for stat in sorted_stats:
        name = stat['dataset_name'][:48]  # Truncate long names
        sum_logger.info(
            f"{name:<50} {stat['num_episodes']:>8} "
            f"{stat['time_per_episode_sec']:>8.2f} {stat['frames_per_episode']:>10.0f}"
        )

    sum_logger.info("="*80)


def _print_result_summary(result: dict, logger: logging.Logger) -> None:
    """Log formatted summary of detection results."""
    total = result['datasets_processed']
    succeeded = len(result['succeeded'])
    failed = len(result['failed'])

    msg = f"\n📊 Summary: {succeeded}/{total} succeeded, {failed}/{total} failed\n"
    logger.info(msg.strip())

    # Performance summary
    total_time = result.get('total_time_s', 0)
    total_frames = result.get('total_frames', 0)
    avg_time_per_frame = result.get('avg_time_per_frame_s', 0)

    if total_time > 0:
        perf_msg = (
            f"⏱️  Performance: {total_time:.2f}s total, {total_frames} frames, "
            f"{avg_time_per_frame*1000:.1f}ms/frame avg\n"
        )
        logger.info(perf_msg.strip())

    if result["succeeded"]:
        logger.info(f"\n✅ Succeeded ({succeeded}):")
        for ds_uuid in result["succeeded"]:
            logger.info(f"   {ds_uuid}")

    if result["failed"]:
        logger.info(f"\n❌ Failed ({failed}):")
        for ds_uuid, err_msg in result["failed"]:
            # Truncate long error messages
            short_err = err_msg[:80] + "..." if len(err_msg) > 80 else err_msg
            logger.info(f"   {ds_uuid}: {short_err}")

    logger.info("")


def run_local(
    db_file: Path,
    episodes: str,
    sample_ratio: float,
    batch_size: int,
    num_workers: int,
    logger: logging.Logger,
    sum_logger: logging.Logger,
) -> int:
    """Local mode: process datasets sequentially (hardlinks must be pre-created)."""
    # Log execution parameters
    sum_logger.info("="*80)
    sum_logger.info(f"Execution started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sum_logger.info("CLI Parameters:")
    sum_logger.info(f"  --db={db_file}")
    sum_logger.info(f"  --episodes={episodes}")
    sum_logger.info(f"  --sample-ratio={sample_ratio}")
    sum_logger.info(f"  --batch-size={batch_size}")
    sum_logger.info(f"  --num-workers={num_workers}")
    sum_logger.info("="*80)

    result = run_local_detection(
        db_file=db_file,
        summary_logger=sum_logger,
        episodes=episodes,
        sample_ratio=sample_ratio,
        batch_size=batch_size,
        num_workers=num_workers,
        logger=logger,
    )

    if result["datasets_processed"] == 0:
        _print_no_tasks_message(logger)
        sum_logger.info("No tasks processed")
        return 0

    _print_result_summary(result, logger)

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

    # Log detailed episode-level statistics (if available)
    dataset_details = result.get("dataset_details", [])
    if dataset_details:
        _log_detailed_episode_statistics(dataset_details, sum_logger)

    return 0 if not result["failed"] else 1


async def run_server_async(
    db_file: Path,
    host: str,
    port: int,
    heartbeat_interval: float,
    timeout: float,
    logger: logging.Logger,
    sum_logger: logging.Logger,
    episodes: str = "all",
    sample_ratio: float = 0.1,
    batch_size: int = 32,
    num_workers: int = 0,
) -> int:
    """Server mode: start task distribution server."""
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
        summary_logger=sum_logger,
        host=host,
        port=port,
        heartbeat_interval=heartbeat_interval,
        timeout=timeout,
        logger=logger,
        episodes=episodes,
        sample_ratio=sample_ratio,
        batch_size=batch_size,
        num_workers=num_workers,
    )

    try:
        logger.info("")
        logger.info("🌐 Starting server and listening for connections...")
        logger.info(f"   Clients can connect to: ws://{host if host != '0.0.0.0' else '<server-ip>'}:{port}")
        logger.info("   Press Ctrl+C to stop the server")
        logger.info("")
        await server.start()
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⚠️  Server interrupted by user")
    except Exception as e:
        logger.exception(f"❌ Server error: {e}")
        return 1
    finally:
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 SERVER SHUTDOWN")
        logger.info("=" * 80)
        stats = server.get_statistics()
        logger.info(f"Total datasets processed: {stats['datasets_succeeded'] + stats['datasets_failed']}")
        logger.info(f"✅ Succeeded: {stats['datasets_succeeded']}")
        logger.info(f"❌ Failed: {stats['datasets_failed']}")
        logger.info(f"Total frames: {stats['total_frames']}")
        logger.info(f"Total time: {stats['total_time_s']:.2f}s")
        if stats['total_frames'] > 0:
            logger.info(f"Avg time per frame: {stats['avg_time_per_frame_s']*1000:.1f}ms")
        logger.info("=" * 80)

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


def _validate_num_clients(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Validate and normalize num_clients argument."""
    num_clients = getattr(args, 'num_clients', 1)

    if (args.server or args.local) and num_clients > 1:
        msg = "❌ --num-clients only works with --client mode"
        logger.error(msg)
        raise SystemExit(2)

    if num_clients > 32:
        msg = f"⚠️  Capping num_clients: {num_clients} → 32"
        logger.warning(msg)
        return 32
    if num_clients < 1:
        msg = f"⚠️  Invalid num_clients: {num_clients} → 1"
        logger.warning(msg)
        return 1

    return num_clients


def _validate_database(args: argparse.Namespace, logger: logging.Logger) -> Path | None:
    """Validate database path for server/local modes."""
    if args.client or args.cliet:
        return None

    if args.db is None:
        msg = "❌ --db required for --server/--local modes"
        logger.error(msg)
        raise SystemExit(2)

    db_file = args.db.expanduser().absolute()

    if not db_file.exists():
        msg = f"❌ Database not found: {db_file}"
        logger.error(msg)
        raise SystemExit(2)
    if not db_file.is_file():
        msg = f"❌ Not a file: {db_file}"
        logger.error(msg)
        raise SystemExit(2)

    return db_file


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    # Create timestamped log directory with key parameters
    log_dir_name = _create_log_dir_name(args)
    log_base_dir = Path("logs/dataloader") / log_dir_name
    log_base_dir.mkdir(parents=True, exist_ok=True)

    # Setup main logger (file + console output)
    logger = setup_logger(
        name="dataloader_main",
        log_dir=log_base_dir,
        level=getattr(logging, args.log_level, logging.INFO),
        console_output=True,
    )

    # Setup summary logger (file + console output)
    sum_logger = setup_logger(
        name="dataloader_summary",
        log_dir=log_base_dir,
        level=logging.INFO,
        console_output=True,
    )

    # Validate arguments
    num_clients = _validate_num_clients(args, logger)
    db_file = _validate_database(args, logger)

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
                sum_logger=sum_logger,
                episodes=args.episodes,
                sample_ratio=args.sample_ratio,
                batch_size=args.batch_size,
                num_workers=args.num_workers,
            )
        )

    if args.client or args.cliet:
        server_uri = f"ws://{args.host or 'localhost'}:{args.port}"

        if num_clients > 1:
            return run_multi_clients(
                server_uri=server_uri,
                num_clients=num_clients,
                heartbeat_interval=args.heartbeat_interval,
                log_dir=log_base_dir,
                log_level=args.log_level,
            )

        # Single client
        stats = asyncio.run(
            run_one_client_async(
                server_uri=server_uri,
                heartbeat_interval=args.heartbeat_interval,
                logger=logger,
            )
        )
        return 0 if stats["tasks_failed"] == 0 else 1

    # Default: local mode
    return run_local(
        db_file=db_file,
        episodes=args.episodes,
        sample_ratio=args.sample_ratio,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        logger=logger,
        sum_logger=sum_logger,
    )


if __name__ == "__main__":
    # Set multiprocessing start method for cross-platform compatibility
    mp.set_start_method("spawn", force=True)
    raise SystemExit(main(sys.argv[1:]))

'''
Test harness for DB-backed dataloader detection

- dataloader_test_db.py
  - Simple CLI to:
    - process-one: run `DataloaderDbProcess.process_one_dataset()` once
    - server: run `DataloaderDbServer` (blocks)
    - client: run `DataloaderDbClient` until no task
  - Defaults `--db` to `examples/dataloader_test/datasets_new.db`

USAGE:
# Process one pending dataset
python scripts/dataloader/dataloader_test_db.py --db examples/dataloader_test/datasets_new.db process-one

# Start server
python scripts/dataloader/dataloader_test_db.py --db examples/dataloader_test/datasets_new.db server --host 0.0.0.0 --port 8771

# Start client
python scripts/dataloader/dataloader_test_db.py client --server-uri ws://localhost:8771

'''

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from robocoin_dataset.dataloader.dataloader_db import (
    DataloaderDbClient,
    DataloaderDbProcess,
    DataloaderDbServer,
)

DEFAULT_DB = Path("examples/dataloader_test/datasets_new.db").absolute()


def run_process_one(db_file: Path) -> int:
    proc = DataloaderDbProcess(db_file_path=db_file)
    proc.process_one_dataset()
    return 0


async def run_server_async(
    db_file: Path, host: str, port: int, heartbeat_interval: float, timeout: float
) -> int:
    server = DataloaderDbServer(
        db_file_path=db_file,
        host=host,
        port=port,
        heartbeat_interval=heartbeat_interval,
        timeout=timeout,
    )
    await server.start()  # runs forever until interrupted
    return 0


async def run_client_async(server_uri: str, heartbeat_interval: float) -> int:
    client = DataloaderDbClient(server_uri=server_uri, heartbeat_interval=heartbeat_interval)
    await client.run_until_no_task()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test harness for DB-backed dataloader detection",
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

    subparsers = parser.add_subparsers(dest="mode")

    # process-one mode
    subparsers.add_parser(
        "process-one",
        help="Synchronously process a single pending dataset (no server/client)",
    )

    # server mode
    p_server = subparsers.add_parser("server", help="Run dataloader detection server")
    p_server.add_argument("--host", type=str, default="0.0.0.0")
    p_server.add_argument("--port", type=int, default=8771)
    p_server.add_argument("--heartbeat-interval", type=float, default=30.0)
    p_server.add_argument("--timeout", type=float, default=15.0)

    # client mode
    p_client = subparsers.add_parser("client", help="Run a client until no task")
    p_client.add_argument("--server-uri", type=str, default="ws://localhost:8771")
    p_client.add_argument("--heartbeat-interval", type=float, default=10.0)

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_file = args.db.expanduser().absolute()
    mode = args.mode or "process-one"

    if mode == "process-one":
        return run_process_one(db_file)

    if mode == "server":
        return asyncio.run(
            run_server_async(
                db_file=db_file,
                host=args.host,
                port=args.port,
                heartbeat_interval=args.heartbeat_interval,
                timeout=args.timeout,
            )
        )

    if mode == "client":
        return asyncio.run(
            run_client_async(
                server_uri=args.server_uri,
                heartbeat_interval=args.heartbeat_interval,
            )
        )

    print(f"Unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

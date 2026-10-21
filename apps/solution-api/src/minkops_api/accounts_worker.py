"""Application bootstrap retaining the existing worker launch command."""

import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from minkops_platform.accounts.worker import (
    WORKER_LANES,
    cleanup_once,
    process,
    run_forever,
    work_once,
)
from minkops_platform.lanes import LANES as DESK_LANES
from minkops_platform.lanes import Host

__all__ = ["cleanup_once", "process", "work_once", "main"]


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--drain", action="store_true", help="Exit when idle for scale-to-zero hosting"
    )
    parser.add_argument('--lanes', type=int, choices=range(1, WORKER_LANES + 1),
                        default=WORKER_LANES, help='Concurrent runs within provisioned memory')
    parser.add_argument('--desk-lanes', type=int, choices=range(1, 17), default=DESK_LANES,
                        help='Concurrent bill and statement sessions')
    args = parser.parse_args()
    url = os.environ["DATABASE_URL"]
    # Run items are served beside the existing runs, and handed to a successor on exit.
    with Host(url, lanes=args.desk_lanes) as host:
        if args.drain:
            from minkops_platform.worker_hosting import drain

            drain(url, lanes=args.lanes, host=host)
        else:
            run_forever(url, lanes=args.lanes)
    if args.drain and os.getenv("WORKER_JOB_RESOURCE"):
        from minkops_connectors.cloud_run import run_job
        from minkops_platform.worker_hosting import dispatch

        dispatch(url, run_job)


if __name__ == "__main__":
    main()

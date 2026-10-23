"""Worker bootstrap: the lanes that serve run items, hosted for good or drained to idle."""

import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from minkops_platform.lanes import LANES, Host
from minkops_platform.worker_hosting import drain, serve


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain", action="store_true", help="Exit when idle for scale-to-zero hosting")
    parser.add_argument("--lanes", type=int, choices=range(1, 17), default=LANES,
                        help="Concurrent bill and statement sessions")
    args = parser.parse_args()
    url = os.environ["DATABASE_URL"]
    # On exit the host hands the items it still holds to a successor, sessions included.
    with Host(url, lanes=args.lanes) as host:
        if args.drain:
            drain(url, host)
        else:
            serve(url)
    if args.drain and os.getenv("WORKER_JOB_RESOURCE"):
        from minkops_connectors.cloud_run import run_job
        from minkops_platform.worker_hosting import dispatch

        dispatch(url, run_job)


if __name__ == "__main__":
    main()

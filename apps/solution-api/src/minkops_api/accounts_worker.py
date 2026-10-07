"""Application bootstrap retaining the existing worker launch command."""

import logging
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from minkops_platform.accounts.worker import cleanup_once, process, run_forever, work_once

__all__ = ["cleanup_once", "process", "work_once", "main"]


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--drain", action="store_true", help="Exit when idle for scale-to-zero hosting"
    )
    args = parser.parse_args()
    if args.drain:
        from minkops_platform.worker_hosting import drain, dispatch
        from minkops_connectors.cloud_run import run_job

        drain(os.environ["DATABASE_URL"])
        if os.getenv("WORKER_JOB_RESOURCE"):
            dispatch(os.environ["DATABASE_URL"], run_job)
    else:
        run_forever(os.environ["DATABASE_URL"])


if __name__ == "__main__":
    main()

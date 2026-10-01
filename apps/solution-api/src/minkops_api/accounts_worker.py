"""Application bootstrap retaining the existing worker launch command."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from minkops_platform.accounts.worker import cleanup_once, process, run_forever, work_once

__all__ = ["cleanup_once", "process", "work_once", "main"]


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    logging.basicConfig(level=logging.INFO)
    run_forever(os.environ["DATABASE_URL"])


if __name__ == "__main__":
    main()

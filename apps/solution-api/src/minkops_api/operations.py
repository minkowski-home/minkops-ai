"""IAM-private recovery transport for a scale-to-zero runtime.

Cloud Run's invoker IAM authenticates the scheduler before this app is reached.
The deployment enables that check and removes public invoker memberships. This
transport has no user sessions, financial decisions or caller-selected jobs.
"""

import logging
import os

from fastapi import FastAPI, HTTPException

from minkops_connectors.cloud_run import run_job
from minkops_platform.worker_hosting import recover

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger(__name__)


@app.post("/reconcile")
def reconcile():
    """Resume durable authorized work only when the shared reconciler finds it."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(503, "Recovery is temporarily unavailable.")
    try:
        return {"dispatched": bool(recover(url, run_job))}
    except Exception as error:
        # Avoid printing database URLs, provider messages or business payloads.
        logger.error("Recovery failed (%s)", type(error).__name__)
        raise HTTPException(503, "Recovery is temporarily unavailable.") from None

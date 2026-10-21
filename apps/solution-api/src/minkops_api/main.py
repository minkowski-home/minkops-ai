"""Shared solution API bootstrap: environment, middleware and routers only."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTasks

from minkops_api.accounts import router as accounts_router
from minkops_api.attention import router as attention_router
from minkops_api.auth import router as core_router
from minkops_api.desktop import router as desktop_router
from minkops_api.discovery import router as discovery_router
from minkops_api.workspace import router as workspace_router

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI()


def wakes_worker(method, path, status):
    """Only transitions that can release hosted work need a dispatch attempt."""
    return method == 'POST' and status < 400 and (
        path.endswith('/accounts/runs')
        or (path.startswith('/api/desktop/worker/jobs/') and path.endswith('/finish'))
        or ('/attention/' in path and path.endswith('/profile'))
        or ('/attention/bills/' in path and not path.endswith('/bulk-preview'))
        or ('/tasks/' in path and path.endswith('/control')))


@app.middleware("http")
async def private_api_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    # Only committed mutations can make work runnable. Read polling must not
    # open another connection and contend on the global dispatcher lock.
    if (os.getenv("WORKER_JOB_RESOURCE")
            and wakes_worker(request.method, request.url.path, response.status_code)):
        from minkops_connectors.cloud_run import run_job
        from minkops_platform.worker_hosting import dispatch

        tasks = BackgroundTasks()
        if response.background:
            tasks.add_task(response.background)
        tasks.add_task(dispatch, os.environ["DATABASE_URL"], run_job)
        response.background = tasks
    return response


app.include_router(core_router)
app.include_router(workspace_router)
app.include_router(accounts_router)
app.include_router(desktop_router)
app.include_router(discovery_router)
app.include_router(attention_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "Minkops API is running"}

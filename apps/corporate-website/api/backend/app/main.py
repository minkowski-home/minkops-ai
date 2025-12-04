from fastapi import FastAPI

app = FastAPI(
    title="pluseleven corporate website backend",
    description="Minimal FastAPI service for health checks and future marketing APIs.",
    version="0.1.0",
)


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "corporate-website"}

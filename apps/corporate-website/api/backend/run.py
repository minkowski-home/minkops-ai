import uvicorn

from app.main import app


def main() -> None:
    """Run the FastAPI development server."""
    uvicorn.run(app, host="0.0.0.0", port=5000, reload=True)


if __name__ == "__main__":
    main()

"""Entry point for running the Flask backend locally."""

from app import create_app


app = create_app()


def main() -> None:
    """Run the Flask development server."""
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()

"""Application factory for the corporate website backend."""

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    from .routes import bp as main_bp  # local import to avoid circularity

    app.register_blueprint(main_bp)

    return app

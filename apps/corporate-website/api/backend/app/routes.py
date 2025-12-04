"""Minimal routes for the corporate website Flask backend."""

from flask import Blueprint, jsonify

bp = Blueprint("main", __name__)


@bp.route("/health", methods=["GET"])
def health() -> tuple[dict[str, str], int]:
    """Health-check endpoint for load balancers and CI."""
    return {"status": "ok", "service": "corporate-website"}, 200

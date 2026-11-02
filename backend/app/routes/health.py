from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Report whether the API and its database are reachable."""
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        # Roll back so the session is usable again for the next request.
        db.session.rollback()
        return jsonify({"status": "ok", "database": "error"}), 503
    return jsonify({"status": "ok", "database": "ok"})

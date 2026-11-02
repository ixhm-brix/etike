"""ETIKE API application factory."""

import os

from flask import Flask

from .config import CONFIGS
from .extensions import db, migrate


def create_app(config_name=None):
    """Build and configure a Flask app.

    config_name is "development", "testing" or "production". When it is not
    given we read FLASK_ENV, and default to production so a missing variable
    can never switch debug mode on by accident.
    """
    config_name = config_name or os.environ.get("FLASK_ENV", "production")
    config = CONFIGS[config_name]

    app = Flask(__name__)
    app.config.from_object(config)

    if config_name == "production":
        # Fail fast on the server instead of running half-configured.
        missing = [k for k in ("DATABASE_URL", "SECRET_KEY") if not app.config.get(k)]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")

    db.init_app(app)
    migrate.init_app(app, db)

    from .routes.health import health_bp

    app.register_blueprint(health_bp, url_prefix="/api")

    return app

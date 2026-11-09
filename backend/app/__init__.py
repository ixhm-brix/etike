"""ETIKE API application factory."""

import os

from flask import Flask

from .config import CONFIGS
from .extensions import db, jwt, migrate


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
        required = ("DATABASE_URL", "SECRET_KEY", "JWT_SECRET_KEY")
        missing = [k for k in required if not app.config.get(k)]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from . import models  # noqa: F401  (registers the tables)
    from .auth import auth_bp
    from .auth.decorators import register_jwt_errors
    from .cli import register_commands
    from .errors import register_error_handlers
    from .routes.bookings import bookings_bp
    from .routes.drivers import drivers_bp
    from .routes.health import health_bp
    from .routes.search import search_bp

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(search_bp, url_prefix="/api")
    app.register_blueprint(drivers_bp, url_prefix="/api")
    app.register_blueprint(bookings_bp, url_prefix="/api")

    register_error_handlers(app)
    register_jwt_errors(jwt)
    register_commands(app)

    return app

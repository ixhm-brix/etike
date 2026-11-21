"""ETIKE API application factory."""

import os

from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import CONFIGS
from .extensions import db, jwt, migrate


def check_production(config):
    """Refuse to start a server that is unsafe or half-configured."""
    required = ("DATABASE_URL", "SECRET_KEY", "JWT_SECRET_KEY")
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    weak = [k for k in ("SECRET_KEY", "JWT_SECRET_KEY")
            if config[k] == "change-me" or len(config[k]) < 32]
    if weak:
        raise RuntimeError(f"Use a long random value for: {', '.join(weak)} "
                           "(see .env.example).")
    if config["SECRET_KEY"] == config["JWT_SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY and JWT_SECRET_KEY must be different.")
    if config.get("DEMO_LOGIN"):
        # Demo login opens test accounts without a password.
        raise RuntimeError("DEMO_LOGIN must be off in production.")


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
        check_production(app.config)
        # Behind Nginx: trust its X-Forwarded-Proto/Host so links we build
        # (ticket QR codes) use https and the real domain.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    if app.config["CORS_ORIGINS"]:
        # Only the listed sites; by default the API answers same-origin only.
        CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from . import models  # noqa: F401  (registers the tables)
    from .auth import auth_bp
    from .auth.decorators import register_jwt_errors
    from .cli import register_commands
    from .errors import register_error_handlers
    from .routes.admin import admin_bp
    from .routes.bookings import bookings_bp
    from .routes.drivers import drivers_bp
    from .routes.health import health_bp
    from .routes.messages import messages_bp
    from .routes.payments import payments_bp
    from .routes.ratings import ratings_bp
    from .routes.search import search_bp
    from .routes.tickets import tickets_bp

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(search_bp, url_prefix="/api")
    app.register_blueprint(drivers_bp, url_prefix="/api")
    app.register_blueprint(bookings_bp, url_prefix="/api")
    app.register_blueprint(payments_bp, url_prefix="/api")
    app.register_blueprint(ratings_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")
    app.register_blueprint(tickets_bp, url_prefix="/api")
    app.register_blueprint(messages_bp, url_prefix="/api")

    register_error_handlers(app)
    register_jwt_errors(jwt)
    register_commands(app)

    return app

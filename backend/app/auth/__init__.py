"""Sign-up, log-in and role checks. Tokens are JWTs from Flask-JWT-Extended;
passwords are hashed with Werkzeug and never stored in plain text."""

from .decorators import current_user, role_required
from .routes import auth_bp

__all__ = ["auth_bp", "current_user", "role_required"]

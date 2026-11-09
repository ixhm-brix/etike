from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..errors import ApiError
from ..extensions import db
from ..models import User


def current_user():
    """The logged-in user for this request (set by role_required)."""
    return g.current_user


def role_required(*roles):
    """Require a valid token. With roles given, the user must have one of them.

        @role_required()                # any logged-in user
        @role_required("driver")        # drivers only
    """

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = db.session.get(User, int(get_jwt_identity()))
            if user is None:
                # Token is valid but the account no longer exists.
                raise ApiError(401, "unauthorized", "Please log in again.")
            if roles and user.role not in roles:
                raise ApiError(
                    403, "forbidden", f"Only {' or '.join(roles)} accounts can do this."
                )
            g.current_user = user
            return view(*args, **kwargs)

        return wrapper

    return decorator


def register_jwt_errors(jwt):
    """Return token problems in the API's normal error format, always as 401."""

    def unauthorized(message):
        return {"error": {"code": "unauthorized", "message": message}}, 401

    jwt.unauthorized_loader(lambda reason: unauthorized("Please log in to continue."))
    jwt.invalid_token_loader(
        lambda reason: unauthorized("Your session is not valid. Log in again.")
    )
    jwt.expired_token_loader(
        lambda header, payload: unauthorized("Your session has expired. Log in again.")
    )

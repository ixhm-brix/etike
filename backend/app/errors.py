"""One JSON error format for the whole API:

    {"error": {"code": "not_found", "message": "Booking not found."}}

Validation errors also list the problem fields:

    {"error": {"code": "invalid_input", "message": "...", "fields": {"phone": "..."}}}
"""

from flask import jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields


def bad_request(message, fields=None):
    return ApiError(400, "invalid_input", message, fields)


def not_found(message):
    return ApiError(404, "not_found", message)


def conflict(message, code="conflict"):
    return ApiError(409, code, message)


def error_response(status, code, message, fields=None):
    body = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    return jsonify({"error": body}), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return error_response(err.status, err.code, err.message, err.fields)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        # 404 for unknown URLs, 405 for wrong methods, 400 for broken JSON...
        code = (err.name or "error").lower().replace(" ", "_")
        return error_response(err.code, code, err.description)

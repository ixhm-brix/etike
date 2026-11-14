"""Configuration classes. Every value comes from an environment variable;
nothing secret is stored in code."""

import os
from datetime import timedelta


class BaseConfig:
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)

    # How long an unpaid booking holds its seats.
    BOOKING_HOLD_MINUTES = int(os.environ.get("BOOKING_HOLD_MINUTES", "15"))

    # Other sites allowed to call the API from a browser, comma separated.
    # Empty (the default) allows none: our own pages are served from the same
    # domain through Nginx and need no CORS.
    CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

    # Flutterwave (Rwanda mobile money). Test-mode keys start with FLWSECK_TEST.
    FLW_BASE_URL = os.environ.get("FLW_BASE_URL", "https://api.flutterwave.com")
    FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
    # The "secret hash" set in the Flutterwave dashboard under Webhooks.
    FLW_SECRET_HASH = os.environ.get("FLW_SECRET_HASH")
    # Where Flutterwave sends the customer back after paying, e.g.
    # https://etike.example/payment.html
    FLW_REDIRECT_URL = os.environ.get("FLW_REDIRECT_URL")

    # Africa's Talking SMS. Username "sandbox" uses their sandbox.
    AT_USERNAME = os.environ.get("AT_USERNAME")
    AT_API_KEY = os.environ.get("AT_API_KEY")
    AT_SENDER_ID = os.environ.get("AT_SENDER_ID")

    TESTING = False
    DEBUG = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestConfig(BaseConfig):
    TESTING = True
    # A separate database so tests never touch development data.
    # Falls back to in-memory SQLite so `pytest` works without Docker.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SECRET_KEY = "test-only-key"
    JWT_SECRET_KEY = "test-only-jwt-key-that-is-long-enough-for-hs256"
    BOOKING_HOLD_MINUTES = 15
    # Tests never talk to the real Flutterwave or SMS services.
    FLW_SECRET_KEY = FLW_SECRET_HASH = FLW_REDIRECT_URL = None
    AT_USERNAME = AT_API_KEY = None


class ProductionConfig(BaseConfig):
    pass


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestConfig,
    "production": ProductionConfig,
}

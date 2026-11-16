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

    # MTN MoMo Collections API. Sandbox: https://momodeveloper.mtn.com
    MOMO_BASE_URL = os.environ.get("MOMO_BASE_URL") or "https://sandbox.momodeveloper.mtn.com"
    # "sandbox" for testing; "mtnrwanda" in production.
    MOMO_TARGET_ENVIRONMENT = os.environ.get("MOMO_TARGET_ENVIRONMENT") or "sandbox"
    # Subscription key of the Collections product.
    MOMO_SUBSCRIPTION_KEY = os.environ.get("MOMO_SUBSCRIPTION_KEY")
    # In the sandbox, create these two with `flask momo-create-user`.
    MOMO_API_USER = os.environ.get("MOMO_API_USER")
    MOMO_API_KEY = os.environ.get("MOMO_API_KEY")
    # The sandbox only accepts EUR; production uses RWF.
    MOMO_CURRENCY = os.environ.get("MOMO_CURRENCY") or (
        "EUR" if MOMO_TARGET_ENVIRONMENT == "sandbox" else "RWF"
    )
    # Optional. Address MoMo calls when a payment finishes, e.g.
    # https://etike.example/api/payments/callback. The payment page also
    # checks the status itself, so payments work without it.
    MOMO_CALLBACK_URL = os.environ.get("MOMO_CALLBACK_URL")

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
    # Tests never talk to the real MoMo or SMS services.
    MOMO_SUBSCRIPTION_KEY = MOMO_API_USER = MOMO_API_KEY = MOMO_CALLBACK_URL = None
    MOMO_TARGET_ENVIRONMENT = "sandbox"
    MOMO_CURRENCY = "EUR"
    AT_USERNAME = AT_API_KEY = None


class ProductionConfig(BaseConfig):
    pass


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestConfig,
    "production": ProductionConfig,
}

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


class ProductionConfig(BaseConfig):
    pass


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestConfig,
    "production": ProductionConfig,
}

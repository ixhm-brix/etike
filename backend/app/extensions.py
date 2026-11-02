"""Extension objects live here so any module can import them without
creating circular imports. They are attached to the app in create_app()."""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()

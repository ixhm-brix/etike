"""Admin commands, run on the server until there is an admin dashboard:

    flask --app wsgi approve-driver 0781234567
"""

import click

from . import validation as v
from .errors import ApiError
from .extensions import db
from .models import User


def register_commands(app):
    @app.cli.command("approve-driver")
    @click.argument("phone")
    def approve_driver(phone):
        """Approve a driver after checking their licence, so they can post rides."""
        try:
            phone = v.phone(phone)
        except ApiError as err:
            raise click.ClickException(err.message) from None
        user = db.session.query(User).filter_by(phone=phone).first()
        if user is None or user.driver is None:
            raise click.ClickException(f"No driver account with phone {phone}.")
        user.driver.is_approved = True
        db.session.commit()
        click.echo(f"Approved {user.full_name} ({phone}).")

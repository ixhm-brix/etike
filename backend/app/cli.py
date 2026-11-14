"""Admin commands, run on the server:

    flask --app wsgi create-admin
    flask --app wsgi approve-driver 0781234567
    flask --app wsgi expire-bookings
"""

import os

import click
from werkzeug.security import generate_password_hash

from . import validation as v
from .errors import ApiError
from .extensions import db
from .models import User
from .services.booking_service import release_expired


def register_commands(app):
    @app.cli.command("create-admin")
    def create_admin():
        """Create an admin account.

        Reads ADMIN_NAME, ADMIN_PHONE and ADMIN_PASSWORD from the environment,
        and asks for any that are missing. There are no built-in admin
        credentials anywhere.
        """
        name = os.environ.get("ADMIN_NAME") or click.prompt("Full name")
        phone = os.environ.get("ADMIN_PHONE") or click.prompt("Phone number")
        password = os.environ.get("ADMIN_PASSWORD") or click.prompt(
            "Password (at least 12 characters)", hide_input=True, confirmation_prompt=True
        )
        try:
            phone = v.phone(phone)
        except ApiError as err:
            raise click.ClickException(err.message) from None
        if len(password) < 12:
            raise click.ClickException("Use an admin password of at least 12 characters.")
        if db.session.query(User).filter_by(phone=phone).first():
            raise click.ClickException(f"An account with phone {phone} already exists.")

        db.session.add(User(
            full_name=" ".join(name.split()),
            phone=phone,
            password_hash=generate_password_hash(password),
            role="admin",
        ))
        db.session.commit()
        click.echo(f"Admin account created for {phone}. Log in on the website with it.")

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
        user.driver.rejected_at = None
        db.session.commit()
        click.echo(f"Approved {user.full_name} ({phone}).")

    @app.cli.command("expire-bookings")
    def expire_bookings():
        """Cancel unpaid bookings whose hold has run out and free their seats."""
        count = release_expired()
        click.echo(f"Released {count} expired booking(s).")

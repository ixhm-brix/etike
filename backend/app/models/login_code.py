from ..extensions import db
from .user import utcnow


class LoginCode(db.Model):
    """A one-time code sent by SMS to log in without a password.

    Only a keyed hash of the code is stored. A code works once, for
    CODE_MINUTES, and stops working after MAX_ATTEMPTS wrong tries.
    """

    __tablename__ = "login_codes"
    __table_args__ = (db.Index("ix_login_codes_phone_created", "phone", "created_at"),)

    code_id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(16), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

"""Log in with a code sent by SMS

Revision ID: d3e8a5c61f02
Revises: c7b2f0a91d34
Create Date: 2026-11-17 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3e8a5c61f02'
down_revision = 'c7b2f0a91d34'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('login_codes',
    sa.Column('code_id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=16), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('code_id', name=op.f('pk_login_codes'))
    )
    with op.batch_alter_table('login_codes', schema=None) as batch_op:
        batch_op.create_index('ix_login_codes_phone_created', ['phone', 'created_at'], unique=False)
    # People who log in with a code have no password.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=True)


def downgrade():
    # Code-only accounts get an unusable password so the column can be required again.
    op.execute("UPDATE users SET password_hash = '!' WHERE password_hash IS NULL")
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=False)
    with op.batch_alter_table('login_codes', schema=None) as batch_op:
        batch_op.drop_index('ix_login_codes_phone_created')
    op.drop_table('login_codes')

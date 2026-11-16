"""Payments use MTN MoMo instead of Flutterwave

Revision ID: a4c1e7d29b10
Revises: 862d0004272b
Create Date: 2026-11-16 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4c1e7d29b10'
down_revision = '862d0004272b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint('method', type_='check')
    op.execute("UPDATE payments SET method = 'mtn_momo'")
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_check_constraint('method', "method = 'mtn_momo'")
        batch_op.add_column(sa.Column('failure_reason', sa.String(length=60), nullable=True))
        # Was the Flutterwave checkout page; MoMo is approved on the phone.
        batch_op.drop_column('checkout_url')


def downgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint('method', type_='check')
    op.execute("UPDATE payments SET method = 'momo'")
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_check_constraint('method', "method = 'momo'")
        batch_op.add_column(sa.Column('checkout_url', sa.String(length=500), nullable=True))
        batch_op.drop_column('failure_reason')

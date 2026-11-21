"""Rides: when the driver started and ended them

Revision ID: d8f3b1c4e620
Revises: c2e9a7f15d40
Create Date: 2026-11-21 17:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8f3b1c4e620'
down_revision = 'c2e9a7f15d40'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ride_offers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('ride_offers', schema=None) as batch_op:
        batch_op.drop_column('ended_at')
        batch_op.drop_column('started_at')

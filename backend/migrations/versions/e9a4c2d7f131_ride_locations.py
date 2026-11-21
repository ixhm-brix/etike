"""Ride locations: where the driver's phone was during a ride

Revision ID: e9a4c2d7f131
Revises: d8f3b1c4e620
Create Date: 2026-11-21 19:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9a4c2d7f131'
down_revision = 'd8f3b1c4e620'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ride_locations',
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('offer_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=5), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lng', sa.Float(), nullable=False),
    sa.Column('accuracy_m', sa.Integer(), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('start', 'track', 'end')", name=op.f('ck_ride_locations_kind')),
    sa.ForeignKeyConstraint(['offer_id'], ['ride_offers.offer_id'], name=op.f('fk_ride_locations_offer_id_ride_offers')),
    sa.PrimaryKeyConstraint('location_id', name=op.f('pk_ride_locations'))
    )
    with op.batch_alter_table('ride_locations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ride_locations_offer_id'), ['offer_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ride_locations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ride_locations_offer_id'))
    op.drop_table('ride_locations')

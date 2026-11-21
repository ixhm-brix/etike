"""Car details: colour, year, air conditioning, luggage space

Revision ID: a1c5e9b3d742
Revises: f2b6d8e1a374
Create Date: 2026-11-21 22:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c5e9b3d742'
down_revision = 'f2b6d8e1a374'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vehicles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('colour', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('year', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('has_ac', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('luggage', sa.String(length=6), nullable=True))
        batch_op.create_check_constraint(batch_op.f('ck_vehicles_luggage_allowed'), "luggage IN ('small', 'medium', 'large')")


def downgrade():
    with op.batch_alter_table('vehicles', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('ck_vehicles_luggage_allowed'), type_='check')
        batch_op.drop_column('luggage')
        batch_op.drop_column('has_ac')
        batch_op.drop_column('year')
        batch_op.drop_column('colour')

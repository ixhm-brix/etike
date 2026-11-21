"""Drivers' personal details: national ID number, date of birth, gender, home;
licence number filled in after sign-up

Revision ID: c2e9a7f15d40
Revises: b6f4d2a8c915
Create Date: 2026-11-18 14:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2e9a7f15d40'
down_revision = 'b6f4d2a8c915'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable: drivers who signed up before this fill them in on the driver
    # page, and can't be approved until they do.
    with op.batch_alter_table('drivers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('national_id_number', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('date_of_birth', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('gender', sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column('home_district', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('home_sector', sa.String(length=60), nullable=True))
        batch_op.create_unique_constraint(batch_op.f('uq_drivers_national_id_number'), ['national_id_number'])
        batch_op.create_check_constraint(batch_op.f('ck_drivers_gender_allowed'), "gender IN ('female', 'male')")
        # Drivers sign up first and give their licence number afterwards.
        batch_op.alter_column('license_number', existing_type=sa.String(length=30), nullable=True)


def downgrade():
    with op.batch_alter_table('drivers', schema=None) as batch_op:
        batch_op.alter_column('license_number', existing_type=sa.String(length=30), nullable=False)
        batch_op.drop_constraint(batch_op.f('ck_drivers_gender_allowed'), type_='check')
        batch_op.drop_constraint(batch_op.f('uq_drivers_national_id_number'), type_='unique')
        batch_op.drop_column('home_sector')
        batch_op.drop_column('home_district')
        batch_op.drop_column('gender')
        batch_op.drop_column('date_of_birth')
        batch_op.drop_column('national_id_number')

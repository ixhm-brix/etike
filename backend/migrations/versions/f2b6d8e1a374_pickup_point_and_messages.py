"""Meeting point on rides, and chat messages between passenger and driver

Revision ID: f2b6d8e1a374
Revises: e9a4c2d7f131
Create Date: 2026-11-21 21:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b6d8e1a374'
down_revision = 'e9a4c2d7f131'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ride_offers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pickup_point', sa.String(length=200), nullable=True))

    op.create_table('messages',
    sa.Column('message_id', sa.Integer(), nullable=False),
    sa.Column('booking_id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=False),
    sa.Column('body', sa.String(length=1000), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.booking_id'], name=op.f('fk_messages_booking_id_bookings')),
    sa.ForeignKeyConstraint(['sender_id'], ['users.user_id'], name=op.f('fk_messages_sender_id_users')),
    sa.PrimaryKeyConstraint('message_id', name=op.f('pk_messages'))
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index('ix_messages_booking_created', ['booking_id', 'created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index('ix_messages_booking_created')
    op.drop_table('messages')
    with op.batch_alter_table('ride_offers', schema=None) as batch_op:
        batch_op.drop_column('pickup_point')

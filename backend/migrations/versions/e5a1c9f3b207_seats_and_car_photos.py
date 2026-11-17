"""Seat numbers on bookings, and car photos

Revision ID: e5a1c9f3b207
Revises: d3e8a5c61f02
Create Date: 2026-11-17 15:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a1c9f3b207'
down_revision = 'd3e8a5c61f02'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('seat_numbers', sa.String(length=80), nullable=True))

    op.create_table('booking_seats',
    sa.Column('seat_id', sa.Integer(), nullable=False),
    sa.Column('booking_id', sa.Integer(), nullable=False),
    sa.Column('trip_id', sa.Integer(), nullable=True),
    sa.Column('offer_id', sa.Integer(), nullable=True),
    sa.Column('seat_number', sa.Integer(), nullable=False),
    sa.CheckConstraint('(trip_id IS NULL) <> (offer_id IS NULL)', name=op.f('ck_booking_seats_one_target')),
    sa.CheckConstraint('seat_number >= 1', name=op.f('ck_booking_seats_seat_number_positive')),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.booking_id'], name=op.f('fk_booking_seats_booking_id_bookings')),
    sa.ForeignKeyConstraint(['offer_id'], ['ride_offers.offer_id'], name=op.f('fk_booking_seats_offer_id_ride_offers')),
    sa.ForeignKeyConstraint(['trip_id'], ['bus_trips.trip_id'], name=op.f('fk_booking_seats_trip_id_bus_trips')),
    sa.PrimaryKeyConstraint('seat_id', name=op.f('pk_booking_seats')),
    sa.UniqueConstraint('offer_id', 'seat_number', name='uq_booking_seats_offer_seat'),
    sa.UniqueConstraint('trip_id', 'seat_number', name='uq_booking_seats_trip_seat')
    )
    with op.batch_alter_table('booking_seats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_booking_seats_booking_id'), ['booking_id'], unique=False)

    # Bookings made before seat numbers existed get the lowest free seats.
    op.execute("""
        WITH active AS (
            SELECT booking_id, trip_id, offer_id, seats_booked,
                   SUM(seats_booked) OVER (PARTITION BY trip_id, offer_id ORDER BY booking_id)
                       - seats_booked AS before
            FROM bookings WHERE status IN ('pending', 'confirmed')
        )
        INSERT INTO booking_seats (booking_id, trip_id, offer_id, seat_number)
        SELECT a.booking_id, a.trip_id, a.offer_id, a.before + n
        FROM active a, generate_series(1, a.seats_booked) AS n
    """)
    op.execute("""
        UPDATE bookings b SET seat_numbers = s.numbers
        FROM (SELECT booking_id, string_agg(seat_number::text, ',' ORDER BY seat_number) AS numbers
              FROM booking_seats GROUP BY booking_id) s
        WHERE s.booking_id = b.booking_id
    """)

    op.create_table('vehicle_photos',
    sa.Column('photo_id', sa.Integer(), nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.vehicle_id'], name=op.f('fk_vehicle_photos_vehicle_id_vehicles')),
    sa.PrimaryKeyConstraint('photo_id', name=op.f('pk_vehicle_photos')),
    sa.UniqueConstraint('filename', name=op.f('uq_vehicle_photos_filename'))
    )
    with op.batch_alter_table('vehicle_photos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_vehicle_photos_vehicle_id'), ['vehicle_id'], unique=False)


def downgrade():
    with op.batch_alter_table('vehicle_photos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vehicle_photos_vehicle_id'))
    op.drop_table('vehicle_photos')
    with op.batch_alter_table('booking_seats', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_booking_seats_booking_id'))
    op.drop_table('booking_seats')
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('seat_numbers')

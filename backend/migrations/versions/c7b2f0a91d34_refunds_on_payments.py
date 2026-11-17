"""Refund status on payments

Revision ID: c7b2f0a91d34
Revises: a4c1e7d29b10
Create Date: 2026-11-17 09:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7b2f0a91d34'
down_revision = 'a4c1e7d29b10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('refund_status', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            'refund_status', "refund_status IS NULL OR refund_status IN ('due', 'refunded')"
        )


def downgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_constraint('refund_status', type_='check')
        batch_op.drop_column('refunded_at')
        batch_op.drop_column('refund_status')

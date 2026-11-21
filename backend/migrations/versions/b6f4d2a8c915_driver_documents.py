"""Drivers' legal documents, and why a driver was rejected

Revision ID: b6f4d2a8c915
Revises: e5a1c9f3b207
Create Date: 2026-11-18 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6f4d2a8c915'
down_revision = 'e5a1c9f3b207'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('drivers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rejection_reason', sa.String(length=300), nullable=True))

    op.create_table('driver_documents',
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('driver_id', sa.Integer(), nullable=False),
    sa.Column('doc_type', sa.String(length=30), nullable=False),
    sa.Column('filename', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=4), nullable=False),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.driver_id'], name=op.f('fk_driver_documents_driver_id_drivers')),
    sa.PrimaryKeyConstraint('document_id', name=op.f('pk_driver_documents')),
    sa.UniqueConstraint('driver_id', 'doc_type', name='uq_driver_documents_one_per_type'),
    sa.UniqueConstraint('filename', name=op.f('uq_driver_documents_filename'))
    )
    with op.batch_alter_table('driver_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_driver_documents_driver_id'), ['driver_id'], unique=False)


def downgrade():
    with op.batch_alter_table('driver_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_driver_documents_driver_id'))

    op.drop_table('driver_documents')
    with op.batch_alter_table('drivers', schema=None) as batch_op:
        batch_op.drop_column('rejection_reason')

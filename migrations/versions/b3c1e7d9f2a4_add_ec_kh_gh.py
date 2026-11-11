"""Add EC, KH, GH to water_parameters

Revision ID: b3c1e7d9f2a4
Revises: a717e3b2a41f
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3c1e7d9f2a4'
down_revision = 'a717e3b2a41f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('water_parameters') as batch_op:
        batch_op.add_column(sa.Column('ec', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('kh', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('gh', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('water_parameters') as batch_op:
        batch_op.drop_column('gh')
        batch_op.drop_column('kh')
        batch_op.drop_column('ec')

"""Add aquariums.code: short unique tank code (100P, 90P...) used by the importer and MCP tools

Revision ID: e6f4c0a8d3b2
Revises: d5e3b9f7c2a1
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f4c0a8d3b2'
down_revision = 'd5e3b9f7c2a1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('aquariums', sa.Column('code', sa.String(10), nullable=True))
    op.create_unique_constraint('uq_aquariums_code', 'aquariums', ['code'])


def downgrade():
    op.drop_constraint('uq_aquariums_code', 'aquariums', type_='unique')
    op.drop_column('aquariums', 'code')

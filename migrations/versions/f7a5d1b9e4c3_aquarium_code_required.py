"""aquariums.code NOT NULL: every tank needs a code (CSV import and the MCP server use it)

Revision ID: f7a5d1b9e4c3
Revises: e6f4c0a8d3b2
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a5d1b9e4c3'
down_revision = 'e6f4c0a8d3b2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    missing = conn.execute(sa.text("select id, name from aquariums where code is null or code = ''")).fetchall()
    if missing:
        raise RuntimeError('give these tanks a code first: ' + ', '.join(f'{i} {n!r}' for i, n in missing))
    op.alter_column('aquariums', 'code', existing_type=sa.String(10), nullable=False)
    op.create_check_constraint('ck_aquariums_code_not_blank', 'aquariums', "code <> ''")


def downgrade():
    op.drop_constraint('ck_aquariums_code_not_blank', 'aquariums', type_='check')
    op.alter_column('aquariums', 'code', existing_type=sa.String(10), nullable=True)

"""Remove users and aquariums.user_id (app no longer has accounts)

Revision ID: c4d2a8e6b1f3
Revises: b3c1e7d9f2a4
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d2a8e6b1f3'
down_revision = 'b3c1e7d9f2a4'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('aquariums_user_id_fkey', 'aquariums', type_='foreignkey')
    op.drop_index('ix_aquariums_user_id', table_name='aquariums')
    op.drop_column('aquariums', 'user_id')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')


def downgrade():
    # Structural only: the original accounts are gone. All aquariums are assigned
    # to one placeholder user with no usable password -- restore from the pg_dump
    # taken before upgrade if you need the real accounts back.
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('password_hash', sa.String(128), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.execute("INSERT INTO users (id, email, password_hash, display_name, created_at) "
               "VALUES (1, 'owner@waterscribe.local', '!', 'Owner', now())")
    op.execute("SELECT setval('users_id_seq', 1)")
    op.add_column('aquariums', sa.Column('user_id', sa.Integer(), nullable=False, server_default='1'))
    op.alter_column('aquariums', 'user_id', server_default=None)
    op.create_index('ix_aquariums_user_id', 'aquariums', ['user_id'])
    op.create_foreign_key('aquariums_user_id_fkey', 'aquariums', 'users', ['user_id'], ['id'])

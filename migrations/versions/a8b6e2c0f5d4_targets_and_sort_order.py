"""Per-tank target ranges; aquariums.sort_order for the tank switcher; daily CO2 window

Revision ID: a8b6e2c0f5d4
Revises: f7a5d1b9e4c3
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'a8b6e2c0f5d4'
down_revision = 'f7a5d1b9e4c3'
branch_labels = None
depends_on = None

SEED = ['100P', '90P', '45U', 'RM1', 'RM2', 'HQT', 'QT']   # Rob's order; other tanks go after


def upgrade():
    op.add_column('aquariums', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('aquariums', sa.Column('co2_on', sa.Time()))
    op.add_column('aquariums', sa.Column('co2_off', sa.Time()))
    op.create_check_constraint('ck_aquariums_co2_window_pair', 'aquariums', '(co2_on IS NULL) = (co2_off IS NULL)')
    conn = op.get_bind()
    for i, code in enumerate(SEED, 1):
        conn.execute(sa.text('update aquariums set sort_order = :i where code = :c'), {'i': i, 'c': code})
    conn.execute(sa.text(
        'update aquariums a set sort_order = :n + r.rn from '
        '(select id, row_number() over (order by code) rn from aquariums where not (code = any(:seed))) r '
        'where a.id = r.id'), {'n': len(SEED), 'seed': SEED})
    conn.execute(sa.text("update aquariums set co2_on = '04:45', co2_off = '13:45' where code = '100P'"))

    op.create_table(
        'target_ranges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aquarium_id', sa.Integer(), sa.ForeignKey('aquariums.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parameter', sa.String(30), nullable=False),
        sa.Column('min', sa.Float()),
        sa.Column('max', sa.Float()),
        sa.UniqueConstraint('aquarium_id', 'parameter', name='uq_target_ranges_tank_param'),
        sa.CheckConstraint('min IS NULL OR max IS NULL OR min <= max', name='ck_target_ranges_order'),
        sa.CheckConstraint('min IS NOT NULL OR max IS NOT NULL', name='ck_target_ranges_not_empty'),
    )
    op.create_index('ix_target_ranges_aquarium_id', 'target_ranges', ['aquarium_id'])


def downgrade():
    op.drop_index('ix_target_ranges_aquarium_id', 'target_ranges')
    op.drop_table('target_ranges')
    op.drop_constraint('ck_aquariums_co2_window_pair', 'aquariums', type_='check')
    op.drop_column('aquariums', 'co2_off')
    op.drop_column('aquariums', 'co2_on')
    op.drop_column('aquariums', 'sort_order')

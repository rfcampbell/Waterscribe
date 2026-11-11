"""Per-reading storage (readings) and typed events (events)

Replaces water_parameters (one wide row per time) with readings (one row per
measurement, with range/method/quality), and maintenance_log with events
(typed, optional numeric value). Existing rows are converted. Timestamps move
from UTC to local wall-clock time (America/Los_Angeles).

Revision ID: d5e3b9f7c2a1
Revises: c4d2a8e6b1f3
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e3b9f7c2a1'
down_revision = 'c4d2a8e6b1f3'
branch_labels = None
depends_on = None

TZ = 'America/Los_Angeles'
OLD_PARAMS = ('temperature', 'ph', 'ammonia', 'nitrite', 'nitrate', 'ec', 'kh', 'gh')
# old maintenance_log.task_type labels -> event keys
OLD_TYPES = {
    'Water Change': 'water_change', 'Filter Cleaning': 'filter_clean', 'Glass Cleaning': 'glass_clean',
    'Gravel Vacuum': 'gravel_vacuum', 'Equipment Check': 'equipment', 'Plant Trimming': 'plant_trim',
    'Other': 'other',
}

def utc_to_local(col):
    return f"(({col} AT TIME ZONE 'UTC') AT TIME ZONE '{TZ}')"

def local_to_utc(col):
    return f"(({col} AT TIME ZONE '{TZ}') AT TIME ZONE 'UTC')"


def upgrade():
    op.create_table(
        'readings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aquarium_id', sa.Integer(), sa.ForeignKey('aquariums.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('time_known', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('parameter', sa.String(30), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('value_min', sa.Float()),
        sa.Column('value_max', sa.Float()),
        sa.Column('method', sa.String(100)),
        sa.Column('quality', sa.String(10), nullable=False, server_default='ok'),
        sa.Column('notes', sa.Text()),
    )
    op.create_index('ix_readings_aquarium_id', 'readings', ['aquarium_id'])
    op.create_index('ix_readings_timestamp', 'readings', ['timestamp'])
    op.create_index('ix_readings_parameter', 'readings', ['parameter'])

    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aquarium_id', sa.Integer(), sa.ForeignKey('aquariums.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('time_known', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('value', sa.Float()),
        sa.Column('notes', sa.Text()),
    )
    op.create_index('ix_events_aquarium_id', 'events', ['aquarium_id'])
    op.create_index('ix_events_timestamp', 'events', ['timestamp'])
    op.create_index('ix_events_event_type', 'events', ['event_type'])

    for p in OLD_PARAMS:
        op.execute(f"""
            INSERT INTO readings (aquarium_id, timestamp, parameter, value, notes)
            SELECT aquarium_id, {utc_to_local('timestamp')}, '{p}', {p}, notes
            FROM water_parameters WHERE {p} IS NOT NULL
        """)

    cases = ' '.join(f"WHEN '{k}' THEN '{v}'" for k, v in OLD_TYPES.items())
    op.execute(f"""
        INSERT INTO events (aquarium_id, timestamp, event_type, notes)
        SELECT aquarium_id, {utc_to_local('timestamp')},
               CASE task_type {cases} ELSE 'task_completed' END,
               NULLIF(CONCAT_WS(': ',
                   CASE WHEN task_type IN ({', '.join(f"'{k}'" for k in OLD_TYPES)}) THEN NULL ELSE task_type END,
                   description), '')
        FROM maintenance_log
    """)

    op.drop_table('water_parameters')
    op.drop_table('maintenance_log')


def downgrade():
    # Lossy: readings collapse back to one row per (aquarium, timestamp) for the
    # eight original parameters; range/method/quality and newer parameters are
    # dropped. Restore from the pg_dump taken before upgrade for a faithful copy.
    op.create_table(
        'water_parameters',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aquarium_id', sa.Integer(), sa.ForeignKey('aquariums.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        *[sa.Column(p, sa.Float()) for p in OLD_PARAMS],
        sa.Column('notes', sa.Text()),
    )
    op.create_index('ix_water_parameters_aquarium_id', 'water_parameters', ['aquarium_id'])
    op.create_index('ix_water_parameters_timestamp', 'water_parameters', ['timestamp'])
    pivots = ', '.join(f"MAX(value) FILTER (WHERE parameter = '{p}')" for p in OLD_PARAMS)
    op.execute(f"""
        INSERT INTO water_parameters (aquarium_id, timestamp, {', '.join(OLD_PARAMS)}, notes)
        SELECT aquarium_id, {local_to_utc('timestamp')}, {pivots},
               STRING_AGG(DISTINCT notes, '; ')
        FROM readings WHERE parameter IN ({', '.join(f"'{p}'" for p in OLD_PARAMS)})
        GROUP BY aquarium_id, timestamp
    """)

    op.create_table(
        'maintenance_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('aquarium_id', sa.Integer(), sa.ForeignKey('aquariums.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('task_type', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('completed', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index('ix_maintenance_log_aquarium_id', 'maintenance_log', ['aquarium_id'])
    op.create_index('ix_maintenance_log_timestamp', 'maintenance_log', ['timestamp'])
    op.execute(f"""
        INSERT INTO maintenance_log (aquarium_id, timestamp, task_type, description)
        SELECT aquarium_id, {local_to_utc('timestamp')}, event_type,
               CONCAT_WS(' ', value::text, notes)
        FROM events
    """)

    op.drop_table('readings')
    op.drop_table('events')

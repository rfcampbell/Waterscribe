"""
Database models for WaterScribe
Single-user: no accounts, everything is shared
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Aquarium(db.Model):
    """Aquarium model"""
    __tablename__ = 'aquariums'
    __table_args__ = (db.CheckConstraint('(co2_on IS NULL) = (co2_off IS NULL)', name='ck_aquariums_co2_window_pair'),)
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)  # short tank code (100P, 90P...) for import and MCP
    type = db.Column(db.String(50))  # freshwater, saltwater, reef, etc.
    volume_gallons = db.Column(db.Float)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')  # tank switcher order
    co2_on = db.Column(db.Time)    # daily CO2 window, local time; both set or neither (CO2 pH drop tile)
    co2_off = db.Column(db.Time)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    readings = db.relationship('Reading', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    events = db.relationship('Event', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    scheduled_tasks = db.relationship('ScheduledTask', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    fish_inventory = db.relationship('FishInventory', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    targets = db.relationship('TargetRange', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Aquarium {self.name}>'

def _ts(r):
    return {
        'timestamp': r.timestamp.isoformat(timespec='minutes') if r.timestamp else None,
        'time_known': r.time_known,
    }

class Reading(db.Model):
    """One measurement of one parameter. Timestamps are local wall-clock time."""
    __tablename__ = 'readings'

    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    time_known = db.Column(db.Boolean, nullable=False, default=True)  # False: date only (stored at 12:00)
    parameter = db.Column(db.String(30), nullable=False, index=True)   # key in catalog.PARAMETERS
    value = db.Column(db.Float, nullable=False)
    value_min = db.Column(db.Float)
    value_max = db.Column(db.Float)
    method = db.Column(db.String(100))
    quality = db.Column(db.String(10), nullable=False, default='ok')   # ok / suspect / bad
    notes = db.Column(db.Text)

    def to_dict(self):
        return {'id': self.id, 'aquarium_id': self.aquarium_id, **_ts(self),
                'parameter': self.parameter, 'value': self.value,
                'value_min': self.value_min, 'value_max': self.value_max,
                'method': self.method, 'quality': self.quality, 'notes': self.notes}

    def __repr__(self):
        return f'<Reading {self.parameter}={self.value} (Aquarium: {self.aquarium_id})>'

class Event(db.Model):
    """Something done to a tank (water change, CO2 adjustment, dosing...). Local time."""
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    time_known = db.Column(db.Boolean, nullable=False, default=True)
    event_type = db.Column(db.String(30), nullable=False, index=True)  # key in catalog.EVENT_TYPES
    value = db.Column(db.Float)
    notes = db.Column(db.Text)

    def to_dict(self):
        return {'id': self.id, 'aquarium_id': self.aquarium_id, **_ts(self),
                'event_type': self.event_type, 'value': self.value, 'notes': self.notes}

    def __repr__(self):
        return f'<Event {self.event_type} (Aquarium: {self.aquarium_id})>'

class TargetRange(db.Model):
    """Target band for one parameter (or catalog.CO2_DROP) of one tank. Either end may be open."""
    __tablename__ = 'target_ranges'
    __table_args__ = (
        db.UniqueConstraint('aquarium_id', 'parameter', name='uq_target_ranges_tank_param'),
        db.CheckConstraint('min IS NULL OR max IS NULL OR min <= max', name='ck_target_ranges_order'),
        db.CheckConstraint('min IS NOT NULL OR max IS NOT NULL', name='ck_target_ranges_not_empty'),
    )

    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id', ondelete='CASCADE'), nullable=False, index=True)
    parameter = db.Column(db.String(30), nullable=False)
    min = db.Column(db.Float)
    max = db.Column(db.Float)

    def to_dict(self):
        return {'parameter': self.parameter, 'min': self.min, 'max': self.max}

class ScheduledTask(db.Model):
    """Scheduled maintenance tasks"""
    __tablename__ = 'scheduled_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id'), nullable=False, index=True)
    task_name = db.Column(db.String(100), nullable=False)
    frequency_days = db.Column(db.Integer)  # For recurring tasks
    last_completed = db.Column(db.DateTime)
    next_due = db.Column(db.DateTime, index=True)
    description = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True, nullable=False)
    is_recurring = db.Column(db.Boolean, default=True, nullable=False)
    specific_date = db.Column(db.DateTime)  # For one-time tasks
    
    def to_dict(self):
        """Convert to dictionary for JSON responses"""
        return {
            'id': self.id,
            'aquarium_id': self.aquarium_id,
            'task_name': self.task_name,
            'frequency_days': self.frequency_days,
            'last_completed': self.last_completed.isoformat() if self.last_completed else None,
            'next_due': self.next_due.isoformat() if self.next_due else None,
            'description': self.description,
            'active': self.active,
            'is_recurring': self.is_recurring,
            'specific_date': self.specific_date.isoformat() if self.specific_date else None
        }
    
    def __repr__(self):
        return f'<ScheduledTask {self.task_name} (Aquarium: {self.aquarium_id})>'

class FishInventory(db.Model):
    """Fish inventory tracking"""
    __tablename__ = 'fish_inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id'), nullable=False, index=True)
    species = db.Column(db.String(100), nullable=False)
    common_name = db.Column(db.String(100))
    held = db.Column(db.Integer, default=0, nullable=False)
    planned = db.Column(db.Integer, default=0, nullable=False)
    added_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text)
    image_url = db.Column(db.Text)
    species_info = db.Column(db.Text)  # JSON blob
    
    def to_dict(self):
        """Convert to dictionary for JSON responses"""
        import json as _json
        info = None
        if self.species_info:
            try:
                info = _json.loads(self.species_info)
            except Exception:
                pass
        return {
            'id': self.id,
            'aquarium_id': self.aquarium_id,
            'species': self.species,
            'common_name': self.common_name,
            'held': self.held,
            'planned': self.planned,
            'added_date': self.added_date.isoformat() if self.added_date else None,
            'notes': self.notes,
            'image_url': self.image_url,
            'species_info': info
        }
    
    def __repr__(self):
        return f'<FishInventory {self.species} (Aquarium: {self.aquarium_id})>'
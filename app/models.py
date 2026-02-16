"""
Database models for WaterScribe
All models are user-scoped for multi-user support
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    aquariums = db.relationship('Aquarium', backref='owner', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set user password"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.email}>'

class Aquarium(db.Model):
    """Aquarium model - users can have multiple tanks"""
    __tablename__ = 'aquariums'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50))  # freshwater, saltwater, reef, etc.
    volume_gallons = db.Column(db.Float)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    water_parameters = db.relationship('WaterParameter', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    maintenance_logs = db.relationship('MaintenanceLog', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    scheduled_tasks = db.relationship('ScheduledTask', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    fish_inventory = db.relationship('FishInventory', backref='aquarium', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Aquarium {self.name} (User: {self.user_id})>'

class WaterParameter(db.Model):
    """Water parameter readings"""
    __tablename__ = 'water_parameters'
    
    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    temperature = db.Column(db.Float)
    ph = db.Column(db.Float)
    ammonia = db.Column(db.Float)
    nitrite = db.Column(db.Float)
    nitrate = db.Column(db.Float)
    notes = db.Column(db.Text)
    
    def to_dict(self):
        """Convert to dictionary for JSON responses"""
        return {
            'id': self.id,
            'aquarium_id': self.aquarium_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'temperature': self.temperature,
            'ph': self.ph,
            'ammonia': self.ammonia,
            'nitrite': self.nitrite,
            'nitrate': self.nitrate,
            'notes': self.notes
        }
    
    def __repr__(self):
        return f'<WaterParameter {self.id} (Aquarium: {self.aquarium_id})>'

class MaintenanceLog(db.Model):
    """Maintenance activity log"""
    __tablename__ = 'maintenance_log'
    
    id = db.Column(db.Integer, primary_key=True)
    aquarium_id = db.Column(db.Integer, db.ForeignKey('aquariums.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    task_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    completed = db.Column(db.Boolean, default=True, nullable=False)
    
    def to_dict(self):
        """Convert to dictionary for JSON responses"""
        return {
            'id': self.id,
            'aquarium_id': self.aquarium_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'task_type': self.task_type,
            'description': self.description,
            'completed': self.completed
        }
    
    def __repr__(self):
        return f'<MaintenanceLog {self.id} (Aquarium: {self.aquarium_id})>'

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
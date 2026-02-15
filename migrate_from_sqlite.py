#!/usr/bin/env python3
"""
Migration script to import existing aquarium.db data into the new PostgreSQL schema
Creates a default user and aquarium for the existing data
"""
import sqlite3
import os
from datetime import datetime
from app import create_app
from app.models import db, User, Aquarium, WaterParameter, MaintenanceLog, ScheduledTask, FishInventory

def migrate_data():
    """Migrate data from SQLite to PostgreSQL"""
    
    # Check if SQLite database exists
    sqlite_path = 'aquarium.db'
    if not os.path.exists(sqlite_path):
        print(f"❌ SQLite database not found: {sqlite_path}")
        return False
    
    # Create Flask app and initialize database
    app = create_app('development')  # Use development config for migration
    
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if migration already done
        existing_user = User.query.first()
        if existing_user:
            print("❌ Migration appears to have already been run (users table not empty)")
            return False
        
        print("🚀 Starting migration from SQLite to PostgreSQL...")
        
        # Connect to SQLite database
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        cursor = sqlite_conn.cursor()
        
        try:
            # Create default user
            default_user = User(
                email='admin@waterscribe.local',
                display_name='Admin User'
            )
            default_user.set_password('waterscribe123')  # Change this password!
            db.session.add(default_user)
            db.session.flush()  # Get the user ID
            
            print(f"✅ Created default user: {default_user.email}")
            print(f"🔑 Default password: waterscribe123 (CHANGE THIS!)")
            
            # Create default aquarium
            default_aquarium = Aquarium(
                user_id=default_user.id,
                name='My Aquarium',
                type='Freshwater',
                description='Migrated from single-user setup'
            )
            db.session.add(default_aquarium)
            db.session.flush()  # Get the aquarium ID
            
            print(f"✅ Created default aquarium: {default_aquarium.name}")
            
            # Migrate water parameters
            cursor.execute('SELECT * FROM water_parameters ORDER BY timestamp')
            params_count = 0
            for row in cursor.fetchall():
                param = WaterParameter(
                    aquarium_id=default_aquarium.id,
                    timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else datetime.utcnow(),
                    temperature=row['temperature'],
                    ph=row['ph'],
                    ammonia=row['ammonia'],
                    nitrite=row['nitrite'],
                    nitrate=row['nitrate'],
                    notes=row['notes']
                )
                db.session.add(param)
                params_count += 1
            
            print(f"✅ Migrated {params_count} water parameter readings")
            
            # Migrate maintenance log
            cursor.execute('SELECT * FROM maintenance_log ORDER BY timestamp')
            maint_count = 0
            for row in cursor.fetchall():
                entry = MaintenanceLog(
                    aquarium_id=default_aquarium.id,
                    timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else datetime.utcnow(),
                    task_type=row['task_type'],
                    description=row['description'],
                    completed=bool(row['completed'])
                )
                db.session.add(entry)
                maint_count += 1
            
            print(f"✅ Migrated {maint_count} maintenance log entries")
            
            # Migrate scheduled tasks
            cursor.execute('SELECT * FROM scheduled_tasks ORDER BY next_due')
            tasks_count = 0
            for row in cursor.fetchall():
                task = ScheduledTask(
                    aquarium_id=default_aquarium.id,
                    task_name=row['task_name'],
                    frequency_days=row['frequency_days'],
                    last_completed=datetime.fromisoformat(row['last_completed']) if row['last_completed'] else None,
                    next_due=datetime.fromisoformat(row['next_due']) if row['next_due'] else None,
                    description=row['description'],
                    active=bool(row['active']),
                    is_recurring=bool(row['is_recurring']),
                    specific_date=datetime.fromisoformat(row['specific_date']) if row['specific_date'] else None
                )
                db.session.add(task)
                tasks_count += 1
            
            print(f"✅ Migrated {tasks_count} scheduled tasks")
            
            # Migrate fish inventory
            cursor.execute('SELECT * FROM fish_inventory ORDER BY added_date')
            fish_count = 0
            for row in cursor.fetchall():
                fish = FishInventory(
                    aquarium_id=default_aquarium.id,
                    species=row['species'],
                    common_name=row['common_name'],
                    quantity=row['quantity'],
                    added_date=datetime.fromisoformat(row['added_date']) if row['added_date'] else datetime.utcnow(),
                    notes=row['notes']
                )
                db.session.add(fish)
                fish_count += 1
            
            print(f"✅ Migrated {fish_count} fish inventory items")
            
            # Commit all changes
            db.session.commit()
            
            print("🎉 Migration completed successfully!")
            print("\n📋 Summary:")
            print(f"   • Default user: {default_user.email}")
            print(f"   • Default aquarium: {default_aquarium.name}")
            print(f"   • Water parameters: {params_count}")
            print(f"   • Maintenance entries: {maint_count}")
            print(f"   • Scheduled tasks: {tasks_count}")
            print(f"   • Fish inventory: {fish_count}")
            print("\n🔐 IMPORTANT: Change the default password after first login!")
            print(f"   Email: {default_user.email}")
            print("   Password: waterscribe123")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {e}")
            return False
        
        finally:
            sqlite_conn.close()

if __name__ == '__main__':
    success = migrate_data()
    exit(0 if success else 1)
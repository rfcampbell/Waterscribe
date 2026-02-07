#!/usr/bin/env python3
"""
Database Migration Script - Fixed Version
Properly migrates the scheduled_tasks table to support one-time tasks
"""

import sqlite3
import sys
from pathlib import Path

# Find the database
db_path = Path('aquarium.db')

if not db_path.exists():
    print("Error: Database not found at aquarium.db")
    print("Please run this script from the directory containing aquarium.db")
    sys.exit(1)

print(f"Found database at: {db_path}")
print()

def migrate():
    """Migrate scheduled_tasks table to support one-time tasks"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("Starting migration...")
    print()
    
    # Check current schema
    c.execute("PRAGMA table_info(scheduled_tasks)")
    columns = {row[1]: row for row in c.fetchall()}
    
    print("Current columns:")
    for col_name in columns.keys():
        print(f"  - {col_name}")
    print()
    
    # Check if we need to migrate
    needs_migration = False
    
    if 'is_recurring' not in columns:
        print("✓ Need to add 'is_recurring' column")
        needs_migration = True
    
    if 'specific_date' not in columns:
        print("✓ Need to add 'specific_date' column")
        needs_migration = True
    
    # Check if frequency_days is NOT NULL
    if columns.get('frequency_days') and columns['frequency_days'][3] == 1:  # notnull = 1
        print("✓ Need to make 'frequency_days' nullable")
        needs_migration = True
    
    if not needs_migration:
        print("=" * 60)
        print("Database already up to date - no changes needed")
        print("=" * 60)
        conn.close()
        return
    
    print()
    print("=" * 60)
    print("MIGRATING DATABASE SCHEMA")
    print("=" * 60)
    print()
    
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # Step 1: Get existing data
    c.execute("SELECT * FROM scheduled_tasks")
    existing_tasks = c.fetchall()
    print(f"Found {len(existing_tasks)} existing tasks to preserve")
    
    # Step 2: Create new table with correct schema
    print("Creating new table schema...")
    c.execute("""
        CREATE TABLE scheduled_tasks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            frequency_days INTEGER,
            last_completed DATETIME,
            next_due DATETIME,
            description TEXT,
            active BOOLEAN DEFAULT 1,
            is_recurring BOOLEAN DEFAULT 1,
            specific_date DATETIME
        )
    """)
    print("✓ New table created")
    
    # Step 3: Copy data to new table
    if existing_tasks:
        print(f"Migrating {len(existing_tasks)} existing tasks...")
        for task in existing_tasks:
            # Old schema: id, task_name, frequency_days, last_completed, next_due, description, active
            c.execute("""
                INSERT INTO scheduled_tasks_new 
                (id, task_name, frequency_days, last_completed, next_due, description, active, is_recurring)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, task)
        print(f"✓ Migrated {len(existing_tasks)} tasks (all set as recurring)")
    
    # Step 4: Drop old table and rename new one
    print("Replacing old table...")
    c.execute("DROP TABLE scheduled_tasks")
    c.execute("ALTER TABLE scheduled_tasks_new RENAME TO scheduled_tasks")
    print("✓ Table replaced")
    
    # Step 5: Commit changes
    conn.commit()
    
    print()
    print("=" * 60)
    print("✓ MIGRATION COMPLETE!")
    print("=" * 60)
    print()
    print("Database now supports:")
    print("  - Recurring tasks (every X days)")
    print("  - One-time tasks (specific date)")
    print("  - frequency_days is now optional (nullable)")
    print()
    print(f"All {len(existing_tasks)} existing tasks preserved as recurring tasks")
    print()
    print("Next steps:")
    print("  1. Restart your app: sudo systemctl restart aquarium-tracker")
    print("  2. Try adding a task through the web interface")
    print()
    
    conn.close()

if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"Error during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

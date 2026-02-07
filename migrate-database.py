#!/usr/bin/env python3
"""
Database Migration Script
Adds support for one-time scheduled tasks to existing aquarium tracker databases
"""

import sqlite3
import sys
from pathlib import Path

# Find the database
db_path = Path('aquarium.db')

if not db_path.exists():
    # Try alternate location
    db_path = Path.home() / 'aquarium-tracker' / 'aquarium.db'
    if not db_path.exists():
        print("Error: Database not found at aquarium.db or ~/aquarium-tracker/aquarium.db")
        print("Please run this script from the directory containing aquarium.db")
        sys.exit(1)

print(f"Found database at: {db_path}")
print()

def migrate():
    """Add new columns to scheduled_tasks table"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("Checking database schema...")
    
    # Get current columns
    c.execute("PRAGMA table_info(scheduled_tasks)")
    columns = [row[1] for row in c.fetchall()]
    
    print(f"Current columns: {', '.join(columns)}")
    print()
    
    # Add new columns if they don't exist
    changes_made = False
    
    if 'is_recurring' not in columns:
        print("Adding 'is_recurring' column...")
        c.execute("ALTER TABLE scheduled_tasks ADD COLUMN is_recurring BOOLEAN DEFAULT 1")
        changes_made = True
        print("✓ Added is_recurring column")
    
    if 'specific_date' not in columns:
        print("Adding 'specific_date' column...")
        c.execute("ALTER TABLE scheduled_tasks ADD COLUMN specific_date DATETIME")
        changes_made = True
        print("✓ Added specific_date column")
    
    # Make frequency_days nullable for one-time tasks
    if changes_made:
        print()
        print("Updating existing tasks to be recurring by default...")
        c.execute("UPDATE scheduled_tasks SET is_recurring = 1 WHERE is_recurring IS NULL")
        print("✓ Updated existing tasks")
    
    if changes_made:
        conn.commit()
        print()
        print("=" * 60)
        print("✓ Migration Complete!")
        print("=" * 60)
        print()
        print("Your database now supports:")
        print("  - Recurring tasks (every X days)")
        print("  - One-time tasks (specific date)")
        print()
        print("Restart your app to use the new features:")
        print("  sudo systemctl restart aquarium-tracker")
        print()
    else:
        print()
        print("=" * 60)
        print("Database already up to date - no changes needed")
        print("=" * 60)
        print()
    
    conn.close()

if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)

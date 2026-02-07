#!/usr/bin/env python3
"""
Import Cycling Schedule for 50 Gallon Tank
This script adds all the cycling tasks and schedule to the aquarium tracker
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Find the database
db_path = Path.home() / 'aquarium-tracker' / 'aquarium.db'

if not db_path.exists():
    print(f"Error: Database not found at {db_path}")
    print("Please run this script from the aquarium-tracker directory or update the path.")
    sys.exit(1)

def add_scheduled_task(conn, task_name, frequency_days, description):
    """Add a scheduled task to the database"""
    c = conn.cursor()
    next_due = datetime.now() + timedelta(days=frequency_days)
    
    c.execute('''
        INSERT INTO scheduled_tasks (task_name, frequency_days, next_due, description, active)
        VALUES (?, ?, ?, ?, ?)
    ''', (task_name, frequency_days, next_due.isoformat(), description, 1))
    
    print(f"✓ Added: {task_name} (every {frequency_days} days)")

def add_maintenance_log(conn, task_type, description):
    """Add a maintenance log entry"""
    c = conn.cursor()
    c.execute('''
        INSERT INTO maintenance_log (task_type, description, completed)
        VALUES (?, ?, ?)
    ''', (task_type, description, 1))
    
    print(f"✓ Logged: {task_type}")

def main():
    print("=" * 60)
    print("Aquarium Cycling Schedule Importer - 50 Gallon Tank")
    print("=" * 60)
    print()
    
    conn = sqlite3.connect(db_path)
    
    # Day 1 tasks - log as completed maintenance
    print("Adding Day 1 setup tasks...")
    add_maintenance_log(conn, "Cycle Start - Day 1", 
        "Added FritzZyme 7 (5 oz) + Fritz Ammonium Chloride (1.25 tsp to 2-4 ppm). "
        "Temperature set to 78-80°F. Filter and sponge filter running 24/7.")
    print()
    
    # Recurring testing schedule during cycling
    print("Adding cycling test schedule...")
    
    # Days 4-21: Test every 2-3 days
    add_scheduled_task(conn, "Water Test - Early Cycling (Days 4-21)", 3,
        "Test: Ammonia, Nitrite, Nitrate, KH, pH. "
        "Watch for nitrites to appear (usually days 7-10). "
        "When ammonia drops to 0-0.25 ppm, redose to 2-4 ppm.")
    
    # Days 21-35+: Test every 1-2 days
    add_scheduled_task(conn, "Water Test - Late Cycling (Days 21-35+)", 1,
        "Daily testing once ammonia and nitrites start dropping. "
        "Watch for nitrite spike (can be very high - normal). "
        "If nitrites exceed 5 ppm, do 50% water change.")
    
    # Ammonia dosing reminder
    add_scheduled_task(conn, "Redose Ammonia (if needed)", 3,
        "When ammonia drops to 0-0.25 ppm, redose Fritz Ammonium Chloride "
        "to reach 2-4 ppm. Target: process 2-4 ppm ammonia to 0 in 24 hours.")
    
    # Emergency water change if needed
    add_scheduled_task(conn, "Check Nitrite Level", 2,
        "If nitrites exceed 5 ppm, perform 50% water change. "
        "High nitrites are normal during cycling but can stall above 5 ppm.")
    
    print()
    
    # Post-cycle tasks
    print("Adding post-cycle tasks...")
    
    add_scheduled_task(conn, "Cycle Completion Check", 1,
        "Cycle is complete when: "
        "1) Ammonia processes from 2-4 ppm to 0 within 24 hours, "
        "2) Nitrite reads 0, "
        "3) Nitrates are present (5-40 ppm). "
        "Before adding fish: Do 50% water change to lower nitrates.")
    
    print()
    
    # Stocking plan reminders
    print("Adding stocking plan tasks...")
    
    add_scheduled_task(conn, "QT First Group - 8 Sterbai Cories", 21,
        "Quarantine first group of 8 sterbai corydoras for 2-3 weeks before "
        "adding to main tank. Monitor for diseases and parasites.")
    
    add_scheduled_task(conn, "QT Second Group - 8 Sterbai Cories", 21,
        "Quarantine second group of 8 sterbai corydoras for 2-3 weeks before "
        "adding to main tank. Wait 1 week after first group before adding.")
    
    add_scheduled_task(conn, "Add Ember Tetras", 7,
        "After both cory groups are established (wait 1 week after second group), "
        "add 25-30 ember tetras. Monitor water parameters closely.")
    
    print()
    
    # Regular maintenance after cycling
    print("Adding regular maintenance schedule...")
    
    add_scheduled_task(conn, "Water Change 25%", 7,
        "Perform 25% water change. Vacuum substrate. "
        "Match temperature and dechlorinate new water.")
    
    add_scheduled_task(conn, "Weekly Water Test", 7,
        "Test: Ammonia (should be 0), Nitrite (should be 0), "
        "Nitrate (keep under 20 ppm for sensitive fish), pH, KH.")
    
    add_scheduled_task(conn, "Clean Filter Media", 14,
        "Rinse filter media in old tank water (never tap water). "
        "Replace chemical media if needed.")
    
    add_scheduled_task(conn, "Check Equipment", 7,
        "Verify heater temperature, filter flow rate, air pump operation. "
        "Clean intake tubes if needed.")
    
    add_scheduled_task(conn, "Algae Cleaning", 7,
        "Clean algae from glass, decorations, and equipment. "
        "Some algae is beneficial - don't over-clean.")
    
    print()
    
    # Commit all changes
    conn.commit()
    conn.close()
    
    print("=" * 60)
    print("✓ Import Complete!")
    print("=" * 60)
    print()
    print("Next Steps:")
    print("1. Open your aquarium tracker in the browser")
    print("2. Go to the 'Schedule' tab to see all tasks")
    print("3. Go to the 'Maintenance Log' to see Day 1 setup")
    print("4. As you complete tasks, mark them complete to auto-reschedule")
    print()
    print("Important Cycling Notes:")
    print("- Total timeline: 2-6 weeks (likely 3-4 with Fritz products)")
    print("- Temperature: Keep at 78-80°F for faster cycling")
    print("- Don't clean filter during cycling - you need those bacteria!")
    print("- High nitrites (even 5+ ppm) are normal - don't panic")
    print("- Test daily once things start moving")
    print()
    print("Good luck with your cycle! 🐠")
    print()

if __name__ == '__main__':
    main()

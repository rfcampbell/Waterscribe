# 🎯 One-Time Tasks Update

Your aquarium tracker now supports **both recurring and one-time scheduled tasks**!

## New Features

### Recurring Tasks (Original)
- Tasks that repeat every X days
- Examples: Water changes every 7 days, filter cleaning every 14 days
- When completed, automatically reschedules for the next occurrence

### One-Time Tasks (NEW!)
- Tasks scheduled for a specific date
- Examples: "Add sterbai cories on July 1st", "Start cycling on March 15th"
- When completed, task is marked as done and deactivated
- Perfect for fish stocking plans, cycling milestones, and special events

## How to Update Your Existing Installation

### Step 1: Update Files on Server

```bash
# Copy the new files to your server
scp app.py rcampbell@robix:~/aquarium-tracker/aquarium-tracker/
scp templates/index.html rcampbell@robix:~/aquarium-tracker/aquarium-tracker/templates/
scp migrate-database.py rcampbell@robix:~/aquarium-tracker/aquarium-tracker/
```

### Step 2: Run Database Migration

```bash
# SSH to your server
ssh rcampbell@robix

# Navigate to your aquarium-tracker directory
cd ~/aquarium-tracker/aquarium-tracker

# Run the migration
python3 migrate-database.py
```

This will add the new database columns needed for one-time tasks.

### Step 3: Restart the App

```bash
# Restart the service
sudo systemctl restart aquarium-tracker

# Verify it's running
sudo systemctl status aquarium-tracker
```

## Using One-Time Tasks

### In the Web Interface

1. Go to the **Schedule** tab
2. Click on the task type dropdown - you'll see:
   - "Recurring (every X days)" - original behavior
   - "One-time (specific date)" - NEW!
3. Select "One-time" and you'll see a date picker
4. Enter task name, select the date, add description
5. Click "Add Task"

### Examples of One-Time Tasks

**For Cycling:**
- "Start cycling" - Day 1
- "First water test" - Day 4
- "Add first cory group" - Date after QT completes
- "Add second cory group" - 3 weeks after first
- "Add ember tetras" - 1 week after second cory group

**For General Aquarium:**
- "Replace UV bulb" - Specific date 6 months from install
- "Restock fish food" - When you expect to run out
- "Equipment upgrade" - When new filter arrives
- "Vacation feeding setup" - Day before you leave

## Visual Indicators

Tasks now show icons:
- 🔄 = Recurring task
- 🎯 = One-time task

Due date warnings:
- **Overdue by X days** (red) - Past due date
- **Due today!** (yellow) - Due today
- **X days** (normal) - Future due date

## What Happens When You Complete a Task

**Recurring Tasks:**
- Logs to maintenance history
- Automatically reschedules based on frequency
- Stays active in your schedule

**One-Time Tasks:**
- Logs to maintenance history
- Marked as complete and deactivated
- Removed from active schedule
- Still visible in maintenance log history

## Database Changes

The migration adds two new columns to `scheduled_tasks`:
- `is_recurring` (BOOLEAN) - Whether task repeats
- `specific_date` (DATETIME) - For one-time tasks

Existing tasks are automatically marked as recurring.

## Troubleshooting

**Migration fails:**
```bash
# Check database location
ls -la ~/aquarium-tracker/*/aquarium.db

# Run migration from correct directory
cd /path/to/directory/with/aquarium.db
python3 migrate-database.py
```

**App won't start after update:**
```bash
# Check logs
sudo journalctl -u aquarium-tracker -n 50

# Verify files are in place
ls -la ~/aquarium-tracker/aquarium-tracker/app.py
ls -la ~/aquarium-tracker/aquarium-tracker/templates/index.html

# Try starting manually to see errors
cd ~/aquarium-tracker/aquarium-tracker
source venv/bin/activate
python3 app.py
```

**Can't see new task type option:**
- Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
- Make sure templates/index.html was updated
- Check browser console for JavaScript errors (F12)

## Importing Your Cycling Schedule

Now that you have one-time tasks, you can import your cycling plan with specific dates:

```bash
# Edit import-cycling-schedule.py to use specific dates instead of frequency
# Or create tasks manually through the web interface
```

The cycling schedule can now be set up with exact dates for:
- Day 1: Start cycling
- Day 4-5: First test
- Specific dates for adding fish groups
- Exact water change dates during cycling

Enjoy your enhanced aquarium tracker! 🐠

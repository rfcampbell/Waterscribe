#!/bin/bash

# WaterScribe Renaming Script
# This script updates all references from "Aquarium Tracker" to "WaterScribe"

set -e

echo "=========================================="
echo "Renaming Project to WaterScribe"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "Error: app.py not found. Please run this script from the project root."
    exit 1
fi

echo "Step 1: Creating backup..."
BACKUP_DIR="backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r *.py templates/ *.txt *.sh *.service *.conf *.md "$BACKUP_DIR/" 2>/dev/null || true
echo "✓ Backup created in $BACKUP_DIR"
echo ""

echo "Step 2: Updating Python files..."
# Update app.py
sed -i 's/Aquarium Tracker Application/WaterScribe Application/g' app.py
sed -i 's/Aquarium Tracker/WaterScribe/g' app.py
sed -i 's/aquarium tracker/WaterScribe/g' app.py
sed -i 's/aquarium-tracker/waterscribe/g' app.py
echo "✓ Updated app.py"

# Update migration scripts
for file in migrate*.py import*.py; do
    if [ -f "$file" ]; then
        sed -i 's/Aquarium Tracker/WaterScribe/g' "$file"
        sed -i 's/aquarium tracker/WaterScribe/g' "$file"
        sed -i 's/aquarium-tracker/waterscribe/g' "$file"
        echo "✓ Updated $file"
    fi
done

echo ""
echo "Step 3: Updating HTML/Frontend..."
sed -i 's/Aquarium Tracker/WaterScribe/g' templates/index.html
sed -i 's/<title>.*<\/title>/<title>WaterScribe<\/title>/g' templates/index.html
echo "✓ Updated templates/index.html"

echo ""
echo "Step 4: Updating configuration files..."
# Update systemd service
if [ -f "aquarium-tracker.service" ]; then
    sed -i 's/Aquarium Tracker/WaterScribe/g' aquarium-tracker.service
    sed -i 's/aquarium-tracker/waterscribe/g' aquarium-tracker.service
    mv aquarium-tracker.service waterscribe.service
    echo "✓ Renamed aquarium-tracker.service -> waterscribe.service"
fi

# Update nginx config
if [ -f "nginx-aquarium-tracker.conf" ]; then
    sed -i 's/aquarium-tracker/waterscribe/g' nginx-aquarium-tracker.conf
    sed -i 's/Aquarium Tracker/WaterScribe/g' nginx-aquarium-tracker.conf
    mv nginx-aquarium-tracker.conf nginx-waterscribe.conf
    echo "✓ Renamed nginx-aquarium-tracker.conf -> nginx-waterscribe.conf"
fi

# Update install script
if [ -f "install-auto.sh" ]; then
    sed -i 's/Aquarium Tracker/WaterScribe/g' install-auto.sh
    sed -i 's/aquarium-tracker/waterscribe/g' install-auto.sh
    echo "✓ Updated install-auto.sh"
fi

# Update backup script
if [ -f "backup.sh" ]; then
    sed -i 's/Aquarium Tracker/WaterScribe/g' backup.sh
    sed -i 's/aquarium-tracker/waterscribe/g' backup.sh
    echo "✓ Updated backup.sh"
fi

echo ""
echo "Step 5: Updating documentation..."
# Update README
if [ -f "README.md" ]; then
    sed -i 's/Aquarium Tracker/WaterScribe/g' README.md
    sed -i 's/aquarium-tracker/waterscribe/g' README.md
    sed -i 's/aquarium tracker/WaterScribe/g' README.md
    echo "✓ Updated README.md"
fi

# Update other markdown files
for file in *.md; do
    if [ -f "$file" ] && [ "$file" != "README.md" ]; then
        sed -i 's/Aquarium Tracker/WaterScribe/g' "$file"
        sed -i 's/aquarium-tracker/waterscribe/g' "$file"
        sed -i 's/aquarium tracker/WaterScribe/g' "$file"
        echo "✓ Updated $file"
    fi
done

echo ""
echo "Step 6: Renaming database file (optional)..."
if [ -f "aquarium.db" ]; then
    echo "Found aquarium.db - would you like to rename it to waterscribe.db?"
    echo "Note: This will require updating app.py's DB_PATH"
    echo "(You can do this manually later if preferred)"
    # Not renaming automatically to avoid breaking running instances
fi

echo ""
echo "=========================================="
echo "✓ Renaming Complete!"
echo "=========================================="
echo ""
echo "Summary of changes:"
echo "  - Updated all Python files"
echo "  - Updated HTML templates"
echo "  - Renamed service file to waterscribe.service"
echo "  - Renamed nginx config to nginx-waterscribe.conf"
echo "  - Updated all documentation"
echo ""
echo "Next steps:"
echo "  1. Review the changes: git diff"
echo "  2. Test the application locally"
echo "  3. Commit changes: git add . && git commit -m 'Rebrand to WaterScribe'"
echo "  4. Rename GitHub repo (Settings -> Repository name)"
echo "  5. Update git remote: git remote set-url origin https://github.com/rfcampbell/waterscribe.git"
echo "  6. Push: git push"
echo ""
echo "Backup saved in: $BACKUP_DIR"
echo ""

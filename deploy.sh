#!/bin/bash
# WaterScribe v2 Deployment Script
# Run this script as regular user: ./deploy.sh

set -e

echo "=== WaterScribe v2 Deployment ==="

# Variables
APP_DIR="/home/rcampbell/aquarium-tracker/aquarium-tracker"

cd "$APP_DIR"

echo "=== Setting up Python virtual environment ==="
# Create/update virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Created new virtual environment"
else
    echo "Using existing virtual environment"
fi

# Activate virtual environment and install/upgrade packages
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ -f .env ]; then
    echo "=== Keeping existing .env ==="
else
    echo "=== Creating .env file ==="
    : "${DB_PASSWORD:?Set DB_PASSWORD to the password native-setup.sh printed}"
    cat > .env << EOF
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
FLASK_ENV=production
DATABASE_URL=postgresql://waterscribe:$DB_PASSWORD@localhost/waterscribe
EOF
fi
set -a; . ./.env; set +a

echo "=== Running Flask database migrations ==="
export FLASK_APP=wsgi.py

# Initialize migrations if they don't exist
if [ ! -d "migrations/versions" ] || [ -z "$(ls -A migrations/versions)" ]; then
    echo "Initializing Flask migrations..."
    flask db init || true  # Don't fail if already initialized
    flask db migrate -m "Initial migration" || true
fi

# Run migrations
flask db upgrade

echo "=== Migrating data from SQLite ==="
if [ -f "aquarium.db" ] && [ -f "migrate_from_sqlite.py" ]; then
    echo "Running SQLite to PostgreSQL migration..."
    python migrate_from_sqlite.py
else
    echo "No SQLite database found or migration script missing, skipping data migration."
fi

echo "=== Testing gunicorn startup ==="
# Test that gunicorn can start (run for 5 seconds then kill)
timeout 5s venv/bin/gunicorn --workers 1 --bind 127.0.0.1:5000 wsgi:app || echo "Gunicorn test completed"

echo "=== Starting/restarting WaterScribe service ==="
# Check if systemd service exists before trying to restart it
if systemctl list-unit-files | grep -q "waterscribe.service"; then
    sudo systemctl restart waterscribe
    sudo systemctl status waterscribe --no-pager -l
else
    echo "Warning: waterscribe.service not found. Make sure to run native-setup.sh first with sudo."
    echo "You can test manually with: venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:app"
fi

echo
echo "=== Deployment Complete ==="
echo "Application should be available at:"
echo "- http://localhost (via nginx)"
echo "- http://localhost:5000 (direct to gunicorn, if nginx not configured)"
echo
echo "To check status:"
echo "- systemctl status waterscribe"
echo "- systemctl status nginx"
echo "- systemctl status postgresql"
echo
echo "Logs:"
echo "- journalctl -u waterscribe -f"
echo "- tail -f /var/log/nginx/access.log"
echo "- tail -f /var/log/nginx/error.log"
echo
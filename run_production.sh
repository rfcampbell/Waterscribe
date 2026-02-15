#!/bin/bash
# WaterScribe Production Runner
# Simple production setup without Docker complexity

set -e

echo "🚀 Starting WaterScribe in production mode..."

# Create required directories
mkdir -p logs static media

# Install requirements if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Set production environment
export FLASK_ENV=production
export SECRET_KEY="waterscribe-prod-$(date +%s)"

# Initialize database
echo "🗃️  Initializing database..."
python3 -c "
from waterscribe_prod import create_app
app = create_app('production')
with app.app_context():
    print('Database initialized successfully')
"

# Start gunicorn server
echo "🌐 Starting production server..."
echo "📊 Access: http://localhost:5000"
echo "📊 Access: http://192.168.221.163:5000"
echo "🔄 Press Ctrl+C to stop"

# Run with gunicorn for production
gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 3 \
    --timeout 60 \
    --keep-alive 2 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --log-level info \
    --capture-output \
    waterscribe_prod:app
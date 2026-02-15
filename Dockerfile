# WaterScribe - Production Docker Container
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home --shell /bin/bash app

# Set work directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# Copy application code
COPY --chown=app:app . .

# Copy nginx config
COPY nginx.conf /etc/nginx/sites-available/waterscribe
RUN rm /etc/nginx/sites-enabled/default && \
    ln -s /etc/nginx/sites-available/waterscribe /etc/nginx/sites-enabled/

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create directories
RUN mkdir -p /var/log/waterscribe /app/static /app/media && \
    chown -R app:app /var/log/waterscribe /app

# Initialize database if it doesn't exist
RUN python3 -c "from waterscribe_prod import create_app; create_app().app_context().do_teardown_appcontext(None)" || true

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/api/stats || exit 1

# Expose port
EXPOSE 80

# Run supervisor to manage nginx + gunicorn
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
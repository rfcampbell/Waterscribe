#!/bin/bash

# Aquarium Tracker - Quick Install Script
# Run this script to automatically set up the application

set -e

echo "==================================="
echo "Aquarium Tracker - Installation"
echo "==================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please do not run this script as root. Run as your regular user."
    exit 1
fi

# Get current directory
INSTALL_DIR="$(pwd)"
echo "Installing to: $INSTALL_DIR"
echo ""

# Install system dependencies
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv sqlite3

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install Python packages
echo "Installing Python packages..."
pip install -r requirements.txt

# Initialize database
echo "Initializing database..."
python3 -c "from app import init_db; init_db()"

# Create systemd service
echo "Setting up systemd service..."
SERVICE_FILE="/tmp/aquarium-tracker.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Aquarium Tracker Web Application
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/bin:/usr/local/bin"
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo cp "$SERVICE_FILE" /etc/systemd/system/aquarium-tracker.service
sudo systemctl daemon-reload

# Ask if user wants to enable the service
read -p "Enable service to start on boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl enable aquarium-tracker
    sudo systemctl start aquarium-tracker
    echo "Service enabled and started!"
else
    echo "Service installed but not enabled. Start manually with: sudo systemctl start aquarium-tracker"
fi

# Ask about Nginx
echo ""
read -p "Install and configure Nginx reverse proxy? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo apt install -y nginx
    
    read -p "Enter your domain name or server IP: " DOMAIN
    
    NGINX_CONF="/etc/nginx/sites-available/aquarium-tracker"
    
    sudo tee "$NGINX_CONF" > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}
EOF
    
    sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl restart nginx
    
    # Configure firewall if UFW is active
    if command -v ufw &> /dev/null; then
        sudo ufw allow 80/tcp
        sudo ufw allow 443/tcp
    fi
    
    echo "Nginx configured for $DOMAIN"
    
    # Ask about SSL
    read -p "Install SSL certificate with Let's Encrypt? (requires valid domain) (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo apt install -y certbot python3-certbot-nginx
        sudo certbot --nginx -d "$DOMAIN"
    fi
fi

echo ""
echo "==================================="
echo "Installation Complete!"
echo "==================================="
echo ""
echo "Access your aquarium tracker at:"
if [ -n "$DOMAIN" ]; then
    echo "  http://$DOMAIN"
else
    echo "  http://$(hostname -I | awk '{print $1}'):5000"
fi
echo ""
echo "Useful commands:"
echo "  sudo systemctl status aquarium-tracker  - Check status"
echo "  sudo systemctl restart aquarium-tracker - Restart app"
echo "  sudo journalctl -u aquarium-tracker -f  - View logs"
echo ""
echo "Database location: $INSTALL_DIR/aquarium.db"
echo "Backup regularly with: cp aquarium.db aquarium-backup-\$(date +%Y%m%d).db"
echo ""

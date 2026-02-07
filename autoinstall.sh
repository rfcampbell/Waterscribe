#!/bin/bash

# Aquarium Tracker - Fully Automated Installation Script
# This script handles everything: dependencies, setup, configuration, and deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

check_root() {
    if [ "$EUID" -eq 0 ]; then
        print_error "Please do not run this script as root. Run as your regular user."
        exit 1
    fi
}

get_script_dir() {
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
}

# Main installation
main() {
    print_header "Aquarium Tracker - Automated Installation"
    echo ""
    
    check_root
    
    INSTALL_DIR=$(get_script_dir)
    print_info "Installation directory: $INSTALL_DIR"
    echo ""
    
    # Check if we're in the right directory
    if [ ! -f "$INSTALL_DIR/app.py" ]; then
        print_error "app.py not found in current directory!"
        print_info "Please run this script from the directory containing app.py"
        exit 1
    fi
    
    # Step 1: Update system and install dependencies
    print_header "Step 1: Installing System Dependencies"
    print_info "Updating package lists..."
    sudo apt update -qq
    
    print_info "Installing required packages..."
    sudo apt install -y python3 python3-pip python3-venv sqlite3 > /dev/null 2>&1
    print_success "System dependencies installed"
    echo ""
    
    # Step 2: Create and activate virtual environment
    print_header "Step 2: Setting Up Python Environment"
    
    if [ -d "$INSTALL_DIR/venv" ]; then
        print_info "Removing existing virtual environment..."
        rm -rf "$INSTALL_DIR/venv"
    fi
    
    print_info "Creating virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
    print_success "Virtual environment created"
    
    # Activate virtual environment
    source "$INSTALL_DIR/venv/bin/activate"
    
    print_info "Installing Python packages..."
    pip install --quiet --upgrade pip
    pip install --quiet -r "$INSTALL_DIR/requirements.txt"
    print_success "Python packages installed"
    echo ""
    
    # Step 3: Create templates directory if missing
    print_header "Step 3: Verifying File Structure"
    
    if [ ! -d "$INSTALL_DIR/templates" ]; then
        print_info "Creating templates directory..."
        mkdir -p "$INSTALL_DIR/templates"
    fi
    
    # Check for index.html
    if [ ! -f "$INSTALL_DIR/templates/index.html" ]; then
        print_error "templates/index.html not found!"
        print_info "Please ensure index.html is in the templates/ directory"
        exit 1
    fi
    
    print_success "File structure verified"
    echo ""
    
    # Step 4: Initialize database
    print_header "Step 4: Initializing Database"
    
    if [ -f "$INSTALL_DIR/aquarium.db" ]; then
        print_info "Database already exists, skipping initialization"
    else
        print_info "Creating new database..."
        python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); from app import init_db; init_db()"
        print_success "Database initialized"
    fi
    echo ""
    
    # Step 5: Create systemd service
    print_header "Step 5: Setting Up System Service"
    
    SERVICE_FILE="/tmp/aquarium-tracker-$$.service"
    
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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    print_info "Installing systemd service..."
    sudo cp "$SERVICE_FILE" /etc/systemd/system/aquarium-tracker.service
    sudo systemctl daemon-reload
    rm "$SERVICE_FILE"
    print_success "Service file created"
    
    print_info "Enabling service to start on boot..."
    sudo systemctl enable aquarium-tracker > /dev/null 2>&1
    print_success "Service enabled"
    
    print_info "Starting service..."
    sudo systemctl start aquarium-tracker
    sleep 2
    
    # Check if service started successfully
    if sudo systemctl is-active --quiet aquarium-tracker; then
        print_success "Service started successfully"
    else
        print_error "Service failed to start"
        print_info "Checking logs..."
        sudo journalctl -u aquarium-tracker -n 20 --no-pager
        exit 1
    fi
    echo ""
    
    # Step 6: Configure Nginx (optional)
    print_header "Step 6: Web Server Configuration"
    echo ""
    
    read -p "Would you like to install and configure Nginx? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installing Nginx..."
        sudo apt install -y nginx > /dev/null 2>&1
        print_success "Nginx installed"
        
        echo ""
        read -p "Enter your domain name or server IP address: " DOMAIN
        
        if [ -z "$DOMAIN" ]; then
            DOMAIN=$(hostname -I | awk '{print $1}')
            print_info "No domain entered, using IP: $DOMAIN"
        fi
        
        NGINX_CONF="/etc/nginx/sites-available/aquarium-tracker"
        
        print_info "Creating Nginx configuration..."
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
        
        # WebSocket support (if needed in future)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml+rss application/json;

    # Logging
    access_log /var/log/nginx/aquarium-tracker.access.log;
    error_log /var/log/nginx/aquarium-tracker.error.log;
}
EOF
        
        print_info "Enabling site..."
        sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
        
        # Remove default site if it exists
        if [ -f /etc/nginx/sites-enabled/default ]; then
            sudo rm /etc/nginx/sites-enabled/default
        fi
        
        print_info "Testing Nginx configuration..."
        if sudo nginx -t > /dev/null 2>&1; then
            print_success "Nginx configuration valid"
            
            print_info "Restarting Nginx..."
            sudo systemctl restart nginx
            print_success "Nginx configured and running"
            
            # Configure firewall if UFW is available
            if command -v ufw > /dev/null 2>&1; then
                print_info "Configuring firewall..."
                sudo ufw allow 80/tcp > /dev/null 2>&1
                sudo ufw allow 443/tcp > /dev/null 2>&1
                print_success "Firewall rules added"
            fi
            
            USING_NGINX=true
        else
            print_error "Nginx configuration test failed"
            sudo nginx -t
        fi
        
        echo ""
        
        # SSL Certificate (optional)
        read -p "Would you like to install an SSL certificate with Let's Encrypt? (requires valid domain) (y/n) " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Installing Certbot..."
            sudo apt install -y certbot python3-certbot-nginx > /dev/null 2>&1
            
            print_info "Obtaining SSL certificate..."
            echo ""
            if sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || sudo certbot --nginx -d "$DOMAIN"; then
                print_success "SSL certificate installed"
                USING_SSL=true
            else
                print_error "SSL certificate installation failed"
                print_info "You can try again later with: sudo certbot --nginx -d $DOMAIN"
            fi
        fi
    else
        print_info "Skipping Nginx configuration"
        USING_NGINX=false
    fi
    
    echo ""
    
    # Step 7: Create backup script
    print_header "Step 7: Setting Up Backup System"
    
    BACKUP_SCRIPT="$INSTALL_DIR/backup.sh"
    
    cat > "$BACKUP_SCRIPT" << 'EOF'
#!/bin/bash
# Aquarium Tracker Database Backup Script

BACKUP_DIR="$HOME/aquarium-tracker-backups"
DB_FILE="$HOME/aquarium-tracker/aquarium.db"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/aquarium-backup-$TIMESTAMP.db"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create backup
if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$BACKUP_FILE"
    echo "Backup created: $BACKUP_FILE"
    
    # Keep only last 30 backups
    ls -t "$BACKUP_DIR"/aquarium-backup-*.db | tail -n +31 | xargs -r rm
    echo "Old backups cleaned up"
else
    echo "Error: Database file not found at $DB_FILE"
    exit 1
fi
EOF
    
    chmod +x "$BACKUP_SCRIPT"
    print_success "Backup script created at $BACKUP_SCRIPT"
    
    # Offer to set up automatic backups
    read -p "Would you like to set up automatic daily backups? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Setting up daily backup cron job..."
        
        # Check if cron job already exists
        if ! crontab -l 2>/dev/null | grep -q "aquarium-tracker/backup.sh"; then
            (crontab -l 2>/dev/null; echo "0 2 * * * $BACKUP_SCRIPT >> $INSTALL_DIR/backup.log 2>&1") | crontab -
            print_success "Daily backup scheduled for 2:00 AM"
        else
            print_info "Backup cron job already exists"
        fi
    fi
    
    echo ""
    
    # Final steps
    print_header "Installation Complete!"
    echo ""
    
    print_success "Aquarium Tracker is now installed and running!"
    echo ""
    
    print_info "Access your application at:"
    if [ "$USING_NGINX" = true ]; then
        if [ "$USING_SSL" = true ]; then
            echo -e "  ${GREEN}https://$DOMAIN${NC}"
        else
            echo -e "  ${GREEN}http://$DOMAIN${NC}"
        fi
    else
        echo -e "  ${GREEN}http://$(hostname -I | awk '{print $1}'):5000${NC}"
    fi
    echo ""
    
    print_info "Useful commands:"
    echo "  Check status:    sudo systemctl status aquarium-tracker"
    echo "  View logs:       sudo journalctl -u aquarium-tracker -f"
    echo "  Restart service: sudo systemctl restart aquarium-tracker"
    echo "  Stop service:    sudo systemctl stop aquarium-tracker"
    echo "  Create backup:   $BACKUP_SCRIPT"
    echo ""
    
    print_info "Database location: $INSTALL_DIR/aquarium.db"
    print_info "Backup script:     $BACKUP_SCRIPT"
    echo ""
    
    # Test the application
    print_info "Testing application..."
    sleep 2
    
    if curl -s http://localhost:5000 > /dev/null; then
        print_success "Application is responding correctly"
    else
        print_error "Application may not be responding"
        print_info "Check logs with: sudo journalctl -u aquarium-tracker -n 50"
    fi
    
    echo ""
    print_header "Setup Summary"
    echo "Installation directory: $INSTALL_DIR"
    echo "Python virtual env:     $INSTALL_DIR/venv"
    echo "Database file:          $INSTALL_DIR/aquarium.db"
    echo "Service name:           aquarium-tracker"
    [ "$USING_NGINX" = true ] && echo "Web server:             Nginx (configured)"
    [ "$USING_SSL" = true ] && echo "SSL:                    Enabled"
    echo ""
    
    print_success "Enjoy tracking your aquarium! 🐠"
    echo ""
}

# Run main installation
main "$@"

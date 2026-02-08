# Aquarium Tracker - Setup Guide

A beautiful web-based aquarium management system with scheduling, parameter tracking, and maintenance logging.

## Features

- **Water Parameter Tracking**: Log temperature, pH, ammonia, nitrite, and nitrate levels
- **Scheduled Maintenance**: Set up recurring tasks with automatic reminders
- **Maintenance History**: Keep detailed logs of all maintenance activities
- **Fish Inventory**: Track your aquatic life with species information
- **Beautiful Ocean-Themed UI**: Animated bubbles and intuitive design
- **SQLite Database**: Reliable data storage with easy backups

## Installation on Linux Server

### Prerequisites

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3 and pip
sudo apt install python3 python3-pip python3-venv -y

# Install Nginx (optional, for production deployment)
sudo apt install nginx -y
```

### Step 1: Set Up the Application

```bash
# Create application directory
mkdir -p ~/aquarium-tracker
cd ~/aquarium-tracker

# Copy all files to this directory
# - app.py
# - requirements.txt
# - templates/index.html

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Test the Application

```bash
# Run the app directly
python3 app.py

# Visit http://your-server-ip:5000 in your browser
# Press Ctrl+C to stop
```

### Step 3: Set Up as a System Service

```bash
# Edit the service file
nano aquarium-tracker.service

# Update these lines:
# - User=YOUR_USERNAME (e.g., User=john)
# - WorkingDirectory=/path/to/aquarium-tracker (e.g., /home/john/aquarium-tracker)
# - ExecStart=/path/to/aquarium-tracker/venv/bin/python3 app.py

# Copy service file to systemd
sudo cp aquarium-tracker.service /etc/systemd/system/

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable aquarium-tracker
sudo systemctl start aquarium-tracker

# Check status
sudo systemctl status aquarium-tracker
```

### Step 4: Set Up Nginx Reverse Proxy (Optional but Recommended)

```bash
# Edit nginx configuration
sudo nano /etc/nginx/sites-available/aquarium-tracker

# Paste the contents from nginx-aquarium-tracker.conf
# Update 'server_name' with your domain or IP

# Enable the site
sudo ln -s /etc/nginx/sites-available/aquarium-tracker /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

### Step 5: Configure Firewall

```bash
# If using UFW firewall
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Step 6: (Optional) Set Up SSL with Let's Encrypt

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com

# Certificate will auto-renew
```

## Usage

Access your aquarium tracker at:
- With Nginx: http://your-domain.com or http://your-server-ip
- Direct access: http://your-server-ip:5000

### Tabs Overview

1. **Water Parameters**: Log and view temperature, pH, and nitrogen cycle parameters
2. **Schedule**: Create recurring maintenance tasks (water changes, filter cleaning, etc.)
3. **Maintenance Log**: Record all maintenance activities
4. **Fish Inventory**: Track your fish species and quantities

## Database

The application uses SQLite with the database stored at `aquarium.db` in the application directory.

### Backup Your Data

```bash
# Create backup
cp ~/aquarium-tracker/aquarium.db ~/aquarium-tracker/backup-$(date +%Y%m%d).db

# Restore from backup
cp ~/aquarium-tracker/backup-20240101.db ~/aquarium-tracker/aquarium.db
```

### Manual Database Access

```bash
# Open database
sqlite3 ~/aquarium-tracker/aquarium.db

# View tables
.tables

# Query data
SELECT * FROM water_parameters ORDER BY timestamp DESC LIMIT 10;

# Exit
.quit
```

## Maintenance Commands

```bash
# View service logs
sudo journalctl -u aquarium-tracker -f

# Restart service
sudo systemctl restart aquarium-tracker

# Stop service
sudo systemctl stop aquarium-tracker

# Check service status
sudo systemctl status aquarium-tracker
```

## Troubleshooting

### App won't start
```bash
# Check logs
sudo journalctl -u aquarium-tracker -n 50

# Test manually
cd ~/aquarium-tracker
source venv/bin/activate
python3 app.py
```

### Can't connect to app
```bash
# Check if app is running
sudo systemctl status aquarium-tracker

# Check if port is open
sudo netstat -tlnp | grep 5000

# Check firewall
sudo ufw status
```

### Database errors
```bash
# Check file permissions
ls -la ~/aquarium-tracker/aquarium.db

# Fix permissions if needed
chmod 664 ~/aquarium-tracker/aquarium.db
```

## Customization

### Change Port
Edit `app.py` and modify the last line:
```python
app.run(host='0.0.0.0', port=YOUR_PORT, debug=False)
```

### Modify Design
Edit `templates/index.html` to customize colors, fonts, and layout. The CSS variables at the top make it easy to change the color scheme:
```css
:root {
    --deep-ocean: #0a1628;
    --coral: #ff6b9d;
    --seafoam: #4ecdc4;
    /* ... etc */
}
```

## Security Recommendations

1. **Change Flask secret key** (add to app.py):
```python
app.config['SECRET_KEY'] = 'your-secret-key-here'
```

2. **Set debug=False in production** (already done in the setup above)

3. **Use HTTPS** with Let's Encrypt (steps provided above)

4. **Regular backups**: Set up a cron job:
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cp ~/aquarium-tracker/aquarium.db ~/aquarium-tracker/backups/backup-$(date +\%Y\%m\%d).db
```

5. **Update regularly**:
```bash
cd ~/aquarium-tracker
source venv/bin/activate
pip install --upgrade flask flask-cors
```

## Support

For issues or questions:
- Check the logs: `sudo journalctl -u aquarium-tracker -f`
- Verify database: `sqlite3 aquarium.db`
- Test connectivity: `curl http://localhost:5000`

## License

This application is provided as-is for personal use.

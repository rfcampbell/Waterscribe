# 🐠 WaterScribe

<img width="2828" height="1472" alt="image" src="https://github.com/user-attachments/assets/e9a41063-eedb-4ef2-b6c1-21cc672614bb" />


A beautiful, feature-rich web application for tracking aquarium maintenance, water parameters, and fish inventory.

## ✨ Features

- **Water Parameter Logging**: Track temperature, pH, ammonia, nitrite, nitrate
- **Scheduled Maintenance**: Set up recurring tasks with automatic due dates
- **Maintenance History**: Detailed logs of all activities
- **Fish Inventory Management**: Track species, quantities, and notes
- **Beautiful UI**: Ocean-themed design with animated bubbles
- **SQLite Database**: Reliable local storage with easy backups

## 🚀 Quick Start (Easiest Method)

```bash
# 1. Copy all files to your Linux server
scp -r * user@your-server:~/waterscribe/

# 2. SSH into your server
ssh user@your-server

# 3. Navigate to directory
cd ~/waterscribe

# 4. Run the installer
chmod +x install.sh
./install.sh
```

The installer will:
- Install all dependencies
- Set up Python virtual environment
- Create systemd service
- Optionally configure Nginx
- Optionally install SSL certificate

## 📋 Manual Installation

### Prerequisites
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

### Install
```bash
cd ~/waterscribe
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Visit `http://your-server-ip:5000`

## 📁 Files Included

- `app.py` - Main Flask application
- `templates/index.html` - Frontend interface
- `requirements.txt` - Python dependencies
- `install.sh` - Automated installation script
- `waterscribe.service` - Systemd service file
- `nginx-waterscribe.conf` - Nginx configuration
- `SETUP_GUIDE.md` - Detailed setup instructions

## 🎨 Interface

The app features four main sections:

1. **Water Parameters** - Log and view water chemistry
2. **Schedule** - Manage recurring maintenance tasks
3. **Maintenance Log** - Record completed activities
4. **Fish Inventory** - Track your aquatic life

## 🔧 Configuration

### Change Port
Edit `app.py`, line at bottom:
```python
app.run(host='0.0.0.0', port=YOUR_PORT)
```

### Customize Colors
Edit `templates/index.html`, CSS variables at top:
```css
:root {
    --deep-ocean: #0a1628;
    --coral: #ff6b9d;
    --seafoam: #4ecdc4;
}
```

## 💾 Database

Data is stored in SQLite at `aquarium.db`

### Backup
```bash
cp aquarium.db backup-$(date +%Y%m%d).db
```

### View Data
```bash
sqlite3 aquarium.db
SELECT * FROM water_parameters ORDER BY timestamp DESC LIMIT 10;
.quit
```

## 🔐 Security Tips

1. Use Nginx reverse proxy (included in install.sh)
2. Enable SSL with Let's Encrypt (included in install.sh)
3. Regular backups (set up cron job)
4. Keep dependencies updated
5. Don't expose port 5000 directly to internet

## 📊 Common Tasks

### Start/Stop Service
```bash
sudo systemctl start waterscribe
sudo systemctl stop waterscribe
sudo systemctl restart waterscribe
```

### View Logs
```bash
sudo journalctl -u waterscribe -f
```

### Check Status
```bash
sudo systemctl status waterscribe
```

## 🐛 Troubleshooting

**Can't connect to app:**
```bash
sudo systemctl status waterscribe
sudo netstat -tlnp | grep 5000
```

**Database errors:**
```bash
ls -la aquarium.db
chmod 664 aquarium.db
```

**View error logs:**
```bash
sudo journalctl -u waterscribe -n 100
```

## 📱 Access

- **Direct**: `http://your-server-ip:5000`
- **With Nginx**: `http://your-domain.com`
- **With SSL**: `https://your-domain.com`

## 🎯 Usage Tips

1. Log water parameters at least weekly
2. Set up recurring tasks for regular maintenance
3. Check the dashboard for upcoming tasks
4. Back up your database monthly
5. Update fish inventory when adding/removing species

---

**Need help?** Check SETUP_GUIDE.md for detailed instructions or troubleshooting steps.

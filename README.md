# WaterScribe v2 - Multi-User Aquarium Tracking

WaterScribe is a comprehensive aquarium management system with multi-user support, built with Flask and PostgreSQL.

## 🌊 Features

- **Multi-User Support**: Each user can manage multiple aquariums
- **Water Parameters**: Track temperature, pH, ammonia, nitrite, nitrate with trends
- **Maintenance Logging**: Record and track aquarium maintenance activities
- **Scheduled Tasks**: Set up recurring or one-time maintenance reminders  
- **Fish Inventory**: Keep track of fish species and quantities
- **Charts & Analytics**: Visualize water parameter trends over time
- **Responsive Design**: Works on desktop and mobile devices
- **Docker Support**: Easy deployment with Docker Compose

## 🏗️ Architecture

- **Flask** with Blueprint architecture (auth, dashboard, api)
- **PostgreSQL** database with SQLAlchemy ORM
- **Flask-Login** for session management
- **Flask-Migrate** for database migrations
- **Gunicorn** WSGI server behind nginx reverse proxy
- **Docker Compose** for orchestration

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/rfcampbell/waterscribe-dev.git
cd waterscribe-dev
git checkout v2-multiuser
```

### 2. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your secrets:
# - Generate a secure SECRET_KEY
# - Set a strong POSTGRES_PASSWORD
```

### 3. Run with Docker Compose

```bash
docker-compose up --build
```

The application will be available at http://localhost

### 4. Initialize Database

```bash
# Run migrations inside the container
docker-compose exec web python -m flask db upgrade

# OR run the container interactively
docker-compose exec web bash
flask db upgrade
```

## 📊 Migration from v1

If you have an existing `aquarium.db` from the single-user version:

```bash
# Make sure aquarium.db is in the project root
docker-compose exec web python migrate_from_sqlite.py
```

This creates:
- Default user: `admin@waterscribe.local` 
- Default password: `waterscribe123` (⚠️ **CHANGE THIS!**)
- Migrates all existing data to the new schema

## 🛠️ Development Setup

### Local Development (without Docker)

1. **Install Dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Database Setup**
   ```bash
   # Install PostgreSQL locally or use Docker for just the DB
   docker run --name postgres-dev -e POSTGRES_PASSWORD=dev -p 5432:5432 -d postgres:16
   
   # Set DATABASE_URL in .env
   export DATABASE_URL=postgresql://postgres:dev@localhost:5432/waterscribe_dev
   ```

3. **Initialize Flask App**
   ```bash
   export FLASK_APP=wsgi.py
   export FLASK_ENV=development
   flask db upgrade
   flask run
   ```

### Database Migrations

```bash
# Create a new migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Downgrade if needed
flask db downgrade
```

## 📁 Project Structure

```
waterscribe/
├── app/
│   ├── __init__.py          # Application factory
│   ├── config.py            # Configuration classes  
│   ├── models.py            # SQLAlchemy models
│   ├── auth/                # Authentication blueprint
│   │   ├── __init__.py
│   │   ├── routes.py        # Login, register, logout
│   │   └── forms.py         # WTForms
│   ├── dashboard/           # Main UI blueprint
│   │   ├── __init__.py
│   │   └── routes.py        # Dashboard, aquarium management
│   ├── api/                 # JSON API blueprint
│   │   ├── __init__.py
│   │   └── routes.py        # CRUD operations, charts
│   ├── templates/
│   │   ├── base.html        # Base template with ocean theme
│   │   ├── auth/            # Login/register pages
│   │   └── dashboard/       # Main application UI
│   └── static/              # CSS, JavaScript, assets
├── migrations/              # Database migrations
├── docker-compose.yml       # Multi-service orchestration
├── Dockerfile              # App container definition
├── nginx.conf              # Reverse proxy configuration
├── requirements.txt        # Python dependencies
├── wsgi.py                 # WSGI entry point
├── migrate_from_sqlite.py  # v1 to v2 migration script
└── README.md               # This file
```

## 🎨 UI/UX

- **Dark Ocean Theme**: Deep blues and seafoam greens
- **Responsive Design**: Works on phones, tablets, desktop
- **Animated Background**: Floating bubbles for ambiance
- **Intuitive Navigation**: Tab-based interface for different functions
- **Real-time Charts**: Interactive parameter trend visualization

## 🔐 Security

- **Password Hashing**: Bcrypt for secure password storage
- **Session Management**: Flask-Login with secure cookies
- **CSRF Protection**: Built-in with Flask-WTF
- **SQL Injection Prevention**: SQLAlchemy ORM
- **XSS Protection**: Jinja2 template auto-escaping
- **Docker Security**: Non-root user, minimal attack surface

## 📈 API Endpoints

All API endpoints require authentication and are scoped to user's aquariums:

- `GET/POST/DELETE /api/aquarium/{id}/parameters` - Water parameters
- `GET/POST/DELETE /api/aquarium/{id}/maintenance` - Maintenance log  
- `GET/POST/PUT/DELETE /api/aquarium/{id}/scheduled` - Scheduled tasks
- `GET/POST/DELETE /api/aquarium/{id}/fish` - Fish inventory
- `GET /api/aquarium/{id}/parameters/chart` - Chart data
- `GET /api/aquarium/{id}/stats` - Summary statistics

## 🐳 Docker Services

- **web**: Flask application with Gunicorn
- **db**: PostgreSQL 16 database
- **nginx**: Reverse proxy and static file serving

## 🔧 Configuration

Environment variables:

- `SECRET_KEY`: Flask secret key (required)
- `POSTGRES_PASSWORD`: Database password (required)
- `DATABASE_URL`: Full database connection string
- `FLASK_ENV`: development/production
- `SESSION_COOKIE_SECURE`: HTTPS cookie flag

## 📝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

- 📧 Issues: GitHub Issues
- 📖 Documentation: This README and code comments
- 🐛 Bug Reports: Please include steps to reproduce

---

Built with 🌊 for aquarium enthusiasts
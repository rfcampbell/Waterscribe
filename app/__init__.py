"""
Flask application factory for WaterScribe
"""
from flask import Flask
from flask_migrate import Migrate

from app.models import db
from app.config import config

migrate = Migrate()

def create_app(config_name='default'):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Register blueprints
    from app.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Context processors
    @app.context_processor
    def inject_config():
        return dict(config=app.config)

    # Pages are rendered per request: make browsers and the iOS web view revalidate instead of
    # showing a stale copy after a deploy (static files keep nginx's long expiry)
    @app.after_request
    def no_stale_pages(resp):
        if resp.mimetype == 'text/html':
            resp.headers.setdefault('Cache-Control', 'no-cache')
        return resp

    return app
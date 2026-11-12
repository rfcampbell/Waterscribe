"""
Flask application factory for WaterScribe
"""
import hashlib
import os

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

    # nginx serves /static with a 30-day expiry, so every url_for('static', ...) carries a hash of the
    # file's content: a deploy that changes a file changes its URL. Nothing may link /static by hand.
    @app.url_defaults
    def version_static(endpoint, values):
        if endpoint == 'static' and 'filename' in values and 'v' not in values:
            values['v'] = static_hash(app.static_folder, values['filename'])

    # the PWA manifest names its icons, so it is served from here with versioned icon URLs
    @app.route('/manifest.webmanifest')
    def manifest():
        import json
        from flask import url_for, Response
        with open(os.path.join(app.root_path, 'manifest.json')) as f:
            m = json.load(f)
        for icon in m.get('icons', []):
            icon['src'] = url_for('static', filename=icon['src'])
        return Response(json.dumps(m, indent=2), mimetype='application/manifest+json',
                        headers={'Cache-Control': 'no-cache'})

    # Pages are rendered per request: make browsers and the iOS web view revalidate instead of
    # showing a stale copy after a deploy (static files keep nginx's long expiry)
    @app.after_request
    def no_stale_pages(resp):
        if resp.mimetype == 'text/html':
            resp.headers.setdefault('Cache-Control', 'no-cache')
        return resp

    return app


_hashes = {}


def static_hash(folder, filename):
    """First 10 hex of the file's sha256, cached until its mtime or size changes; '0' if missing."""
    path = os.path.join(folder, filename)
    try:
        st = os.stat(path)
    except OSError:
        return '0'
    key = (path, st.st_mtime_ns, st.st_size)
    if key not in _hashes:
        with open(path, 'rb') as f:
            _hashes[key] = hashlib.sha256(f.read()).hexdigest()[:10]
    return _hashes[key]

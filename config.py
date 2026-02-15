#!/usr/bin/env python3
"""
WaterScribe Configuration
Environment-based configuration for production deployment
"""

import os
from pathlib import Path

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-me'
    
    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///aquarium.db'
    DB_PATH = Path(DATABASE_URL.replace('sqlite:///', ''))
    
    # App settings
    DEBUG = False
    TESTING = False
    
    # CORS settings
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')
    
    # File uploads
    UPLOAD_FOLDER = Path('media')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = Path('logs/waterscribe.log')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SECRET_KEY = 'dev-secret-key'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    # Stricter CORS in production
    if os.environ.get('CORS_ORIGINS') is None:
        CORS_ORIGINS = ['http://localhost', 'https://your-domain.com']

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DATABASE_URL = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
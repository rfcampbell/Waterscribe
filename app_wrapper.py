#!/usr/bin/env python3
"""
Wrapper script to run enhanced Waterscribe app
This gets called by systemd service instead of the original app.py
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the enhanced app
from app_dev import app, init_db

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
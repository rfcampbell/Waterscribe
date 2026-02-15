#!/usr/bin/env python3
"""
Chart API module for WaterScribe
Adds chart endpoints to the existing Flask app
"""

from flask import jsonify, request
from datetime import datetime
import sqlite3
from pathlib import Path

# Database setup
DB_PATH = Path(__file__).parent / 'aquarium.db'

def get_db():
    """Get database connection with proper timeout"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def add_chart_routes(app):
    """Add chart API routes to existing Flask app"""
    
    @app.route('/api/parameters/chart')
    def parameters_chart():
        """Get parameter data formatted for charts"""
        conn = get_db()
        
        try:
            days = request.args.get('days', 30, type=int)
            c = conn.cursor()
            
            c.execute('''
                SELECT * FROM water_parameters 
                WHERE timestamp >= datetime('now', '-{} days')
                ORDER BY timestamp ASC
            '''.format(days))
            
            rows = c.fetchall()
            
            # Format data for Chart.js
            chart_data = {
                'labels': [],
                'datasets': {
                    'temperature': {'label': 'Temperature (°F)', 'data': [], 'borderColor': '#ff6b9d', 'backgroundColor': 'rgba(255, 107, 157, 0.1)'},
                    'ph': {'label': 'pH', 'data': [], 'borderColor': '#4ecdc4', 'backgroundColor': 'rgba(78, 205, 196, 0.1)'},
                    'ammonia': {'label': 'Ammonia (ppm)', 'data': [], 'borderColor': '#f7b267', 'backgroundColor': 'rgba(247, 178, 103, 0.1)'},
                    'nitrite': {'label': 'Nitrite (ppm)', 'data': [], 'borderColor': '#2d6a4f', 'backgroundColor': 'rgba(45, 106, 79, 0.1)'},
                    'nitrate': {'label': 'Nitrate (ppm)', 'data': [], 'borderColor': '#2d4a6f', 'backgroundColor': 'rgba(45, 74, 111, 0.1)'}
                }
            }
            
            for row in rows:
                # Format timestamp for display
                try:
                    dt = datetime.fromisoformat(row['timestamp'])
                    chart_data['labels'].append(dt.strftime('%m/%d'))
                except:
                    chart_data['labels'].append(str(row['timestamp'])[:5])
                
                # Add data points (handle None values)
                for param in ['temperature', 'ph', 'ammonia', 'nitrite', 'nitrate']:
                    value = row[param]
                    chart_data['datasets'][param]['data'].append(value)
            
            return jsonify(chart_data)
        
        finally:
            conn.close()
    
    print("✅ Chart API routes added to Flask app")
    return app
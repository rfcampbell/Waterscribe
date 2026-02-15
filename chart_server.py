#!/usr/bin/env python3
"""
Chart API Server for WaterScribe
Lightweight service to provide chart data
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import sqlite3
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Database setup
DB_PATH = Path(__file__).parent / 'aquarium.db'

def get_db():
    """Get database connection with proper timeout"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/parameters/chart')
def parameters_chart():
    """Get parameter data formatted for charts"""
    conn = get_db()
    
    try:
        days = request.args.get('days', 30, type=int)
        c = conn.cursor()
        
        c.execute(f'''
            SELECT * FROM water_parameters 
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC
        ''')
        
        rows = c.fetchall()
        
        # Format data for Chart.js
        chart_data = {
            'labels': [],
            'datasets': {
                'temperature': {'label': 'Temperature (°F)', 'data': [], 'borderColor': '#ff6b9d', 'backgroundColor': 'rgba(255, 107, 157, 0.1)', 'fill': False, 'tension': 0.3},
                'ph': {'label': 'pH', 'data': [], 'borderColor': '#4ecdc4', 'backgroundColor': 'rgba(78, 205, 196, 0.1)', 'fill': False, 'tension': 0.3},
                'ammonia': {'label': 'Ammonia (ppm)', 'data': [], 'borderColor': '#f7b267', 'backgroundColor': 'rgba(247, 178, 103, 0.1)', 'fill': False, 'tension': 0.3},
                'nitrite': {'label': 'Nitrite (ppm)', 'data': [], 'borderColor': '#2d6a4f', 'backgroundColor': 'rgba(45, 106, 79, 0.1)', 'fill': False, 'tension': 0.3},
                'nitrate': {'label': 'Nitrate (ppm)', 'data': [], 'borderColor': '#2d4a6f', 'backgroundColor': 'rgba(45, 74, 111, 0.1)', 'fill': False, 'tension': 0.3}
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
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'chart-api'})

if __name__ == '__main__':
    print("🚀 Starting Chart API server on port 5002...")
    app.run(host='127.0.0.1', port=5002, debug=False)
#!/usr/bin/env python3
from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
CORS(app)

@app.route('/api/parameters/chart')
def chart():
    try:
        # Get real data from database
        DB_PATH = Path('.') / 'aquarium.db'
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        
        c = conn.cursor()
        c.execute('''
            SELECT timestamp, temperature, ph, ammonia, nitrite, nitrate 
            FROM water_parameters 
            WHERE timestamp >= datetime('now', '-30 days')
            ORDER BY timestamp ASC
        ''')
        
        rows = c.fetchall()
        conn.close()
        
        chart_data = {
            'labels': [],
            'datasets': {
                'temperature': {'label': 'Temperature (°F)', 'data': [], 'borderColor': '#ff6b9d', 'fill': False, 'tension': 0.3},
                'ph': {'label': 'pH', 'data': [], 'borderColor': '#4ecdc4', 'fill': False, 'tension': 0.3}
            }
        }
        
        for row in rows:
            # Format date
            try:
                dt = datetime.fromisoformat(row['timestamp'])
                chart_data['labels'].append(dt.strftime('%m/%d'))
            except:
                chart_data['labels'].append(str(row['timestamp'])[:5])
            
            # Add data points
            chart_data['datasets']['temperature']['data'].append(row['temperature'])
            chart_data['datasets']['ph']['data'].append(row['ph'])
        
        return jsonify(chart_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5002, debug=False)
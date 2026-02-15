#!/usr/bin/env python3
"""
WaterScribe Complete - Enhanced Aquarium Tracker
Standalone version with all features working
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
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

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Water parameters table
    c.execute('''
        CREATE TABLE IF NOT EXISTS water_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            ph REAL,
            ammonia REAL,
            nitrite REAL,
            nitrate REAL,
            notes TEXT
        )
    ''')
    
    # Maintenance log table  
    c.execute('''
        CREATE TABLE IF NOT EXISTS maintenance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            task_type TEXT NOT NULL,
            description TEXT,
            completed BOOLEAN DEFAULT 1
        )
    ''')
    
    # Scheduled tasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            frequency_days INTEGER,
            last_completed DATETIME,
            next_due DATETIME,
            description TEXT,
            active BOOLEAN DEFAULT 1,
            is_recurring BOOLEAN DEFAULT 1,
            specific_date DATETIME
        )
    ''')
    
    # Fish inventory table
    c.execute('''
        CREATE TABLE IF NOT EXISTS fish_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species TEXT NOT NULL,
            common_name TEXT,
            quantity INTEGER DEFAULT 1,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# Routes
@app.route('/')
def index():
    """Serve the main application page"""
    return render_template('index_complete.html')

@app.route('/api/parameters', methods=['GET', 'POST', 'PUT', 'DELETE'])
def parameters():
    """Handle water parameter data"""
    conn = get_db()
    
    try:
        if request.method == 'POST':
            data = request.json
            c = conn.cursor()
            local_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''
                INSERT INTO water_parameters (timestamp, temperature, ph, ammonia, nitrite, nitrate, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                local_timestamp,
                data.get('temperature'),
                data.get('ph'),
                data.get('ammonia'),
                data.get('nitrite'),
                data.get('nitrate'),
                data.get('notes')
            ))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid})
        
        elif request.method == 'PUT':
            # Update existing parameter reading
            data = request.json
            param_id = data.get('id')
            
            if not param_id:
                return jsonify({'success': False, 'error': 'ID required'}), 400
            
            c = conn.cursor()
            c.execute('''
                UPDATE water_parameters 
                SET temperature = ?, ph = ?, ammonia = ?, nitrite = ?, nitrate = ?, notes = ?
                WHERE id = ?
            ''', (
                data.get('temperature'),
                data.get('ph'), 
                data.get('ammonia'),
                data.get('nitrite'),
                data.get('nitrate'),
                data.get('notes'),
                param_id
            ))
            conn.commit()
            return jsonify({'success': True})
        
        elif request.method == 'DELETE':
            param_id = request.args.get('id', type=int)
            if not param_id:
                return jsonify({'success': False, 'error': 'ID required'}), 400
            
            c = conn.cursor()
            c.execute('DELETE FROM water_parameters WHERE id = ?', (param_id,))
            conn.commit()
            return jsonify({'success': True})
        
        else:
            # GET: return recent parameters
            limit = request.args.get('limit', 50, type=int)
            c = conn.cursor()
            c.execute('''
                SELECT * FROM water_parameters 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = c.fetchall()
            return jsonify([dict(row) for row in rows])
    
    finally:
        conn.close()

@app.route('/api/parameters/chart')
def parameters_chart():
    """Get parameter data formatted for charts"""
    conn = get_db()
    
    try:
        days = request.args.get('days', 30, type=int)
        c = conn.cursor()
        
        c.execute(f'''
            SELECT timestamp, temperature, ph, ammonia, nitrite, nitrate
            FROM water_parameters 
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC
        ''')
        
        rows = c.fetchall()
        
        chart_data = {
            'labels': [],
            'datasets': {
                'temperature': {'label': 'Temperature (°F)', 'data': [], 'borderColor': '#ff6b9d', 'fill': False, 'tension': 0.3},
                'ph': {'label': 'pH', 'data': [], 'borderColor': '#4ecdc4', 'fill': False, 'tension': 0.3},
                'ammonia': {'label': 'Ammonia (ppm)', 'data': [], 'borderColor': '#f7b267', 'fill': False, 'tension': 0.3},
                'nitrite': {'label': 'Nitrite (ppm)', 'data': [], 'borderColor': '#2d6a4f', 'fill': False, 'tension': 0.3},
                'nitrate': {'label': 'Nitrate (ppm)', 'data': [], 'borderColor': '#2d4a6f', 'fill': False, 'tension': 0.3}
            }
        }
        
        for row in rows:
            try:
                dt = datetime.fromisoformat(row['timestamp'])
                chart_data['labels'].append(dt.strftime('%m/%d'))
            except:
                chart_data['labels'].append(str(row['timestamp'])[:5])
            
            for param in ['temperature', 'ph', 'ammonia', 'nitrite', 'nitrate']:
                value = row[param]
                chart_data['datasets'][param]['data'].append(value)
        
        return jsonify(chart_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        conn.close()

@app.route('/api/maintenance', methods=['GET', 'POST', 'PUT', 'DELETE'])
def maintenance():
    """Handle maintenance log entries"""
    conn = get_db()
    
    try:
        if request.method == 'POST':
            data = request.json
            c = conn.cursor()
            local_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''
                INSERT INTO maintenance_log (timestamp, task_type, description, completed)
                VALUES (?, ?, ?, ?)
            ''', (
                local_timestamp,
                data.get('task_type'),
                data.get('description'),
                data.get('completed', True)
            ))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid})
        
        elif request.method == 'DELETE':
            entry_id = request.args.get('id', type=int)
            if not entry_id:
                return jsonify({'success': False, 'error': 'ID required'}), 400
            
            c = conn.cursor()
            c.execute('DELETE FROM maintenance_log WHERE id = ?', (entry_id,))
            conn.commit()
            return jsonify({'success': True})
        
        else:
            limit = request.args.get('limit', 50, type=int)
            c = conn.cursor()
            c.execute('''
                SELECT * FROM maintenance_log 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = c.fetchall()
            return jsonify([dict(row) for row in rows])
    
    finally:
        conn.close()

@app.route('/api/scheduled', methods=['GET', 'POST', 'PUT', 'DELETE'])
def scheduled():
    """Handle scheduled tasks"""
    conn = get_db()
    
    try:
        c = conn.cursor()
        
        if request.method == 'POST':
            data = request.json
            is_recurring = data.get('is_recurring', True)
            
            if is_recurring:
                if not data.get('frequency_days'):
                    return jsonify({'success': False, 'error': 'Frequency is required for recurring tasks'}), 400
                
                next_due = datetime.now() + timedelta(days=data['frequency_days'])
                c.execute('''
                    INSERT INTO scheduled_tasks (task_name, frequency_days, next_due, description, active, is_recurring)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    data['task_name'],
                    data['frequency_days'],
                    next_due.isoformat(),
                    data.get('description'),
                    True,
                    True
                ))
            else:
                if not data.get('specific_date'):
                    return jsonify({'success': False, 'error': 'Date is required for one-time tasks'}), 400
                
                try:
                    specific_date = datetime.fromisoformat(data['specific_date'])
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid date format'}), 400
                
                c.execute('''
                    INSERT INTO scheduled_tasks (task_name, next_due, description, active, is_recurring, specific_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    data['task_name'],
                    specific_date.isoformat(),
                    data.get('description'),
                    True,
                    False,
                    specific_date.isoformat()
                ))
            
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid})
        
        elif request.method == 'PUT':
            data = request.json
            task_id = data['id']
            
            c.execute('SELECT frequency_days, is_recurring FROM scheduled_tasks WHERE id = ?', (task_id,))
            row = c.fetchone()
            
            if row:
                is_recurring = row['is_recurring']
                now = datetime.now()
                
                if is_recurring:
                    frequency = row['frequency_days']
                    next_due = now + timedelta(days=frequency)
                    
                    c.execute('''
                        UPDATE scheduled_tasks 
                        SET last_completed = ?, next_due = ?
                        WHERE id = ?
                    ''', (now.isoformat(), next_due.isoformat(), task_id))
                else:
                    c.execute('''
                        UPDATE scheduled_tasks 
                        SET last_completed = ?, active = 0
                        WHERE id = ?
                    ''', (now.isoformat(), task_id))
                
                # Log to maintenance
                log_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                c.execute('''
                    INSERT INTO maintenance_log (timestamp, task_type, description)
                    VALUES (?, ?, ?)
                ''', (log_timestamp, data.get('task_name', 'Scheduled Task'), 'Completed scheduled task'))
                
                conn.commit()
            
            return jsonify({'success': True})
        
        elif request.method == 'DELETE':
            task_id = request.args.get('id', type=int)
            c.execute('DELETE FROM scheduled_tasks WHERE id = ?', (task_id,))
            conn.commit()
            return jsonify({'success': True})
        
        else:
            c.execute('''
                SELECT * FROM scheduled_tasks 
                WHERE active = 1
                ORDER BY next_due ASC
            ''')
            
            rows = c.fetchall()
            return jsonify([dict(row) for row in rows])
    
    finally:
        conn.close()

@app.route('/api/fish', methods=['GET', 'POST', 'PUT', 'DELETE'])
def fish():
    """Handle fish inventory"""
    conn = get_db()
    
    try:
        c = conn.cursor()
        
        if request.method == 'POST':
            data = request.json
            
            if not data.get('species'):
                return jsonify({'success': False, 'error': 'Species is required'}), 400
            
            c.execute('''
                INSERT INTO fish_inventory (species, common_name, quantity, notes)
                VALUES (?, ?, ?, ?)
            ''', (
                data['species'],
                data.get('common_name'),
                data.get('quantity', 1),
                data.get('notes')
            ))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid})
        
        elif request.method == 'PUT':
            data = request.json
            fish_id = data.get('id')
            
            if not fish_id:
                return jsonify({'success': False, 'error': 'ID required'}), 400
            
            if not data.get('species'):
                return jsonify({'success': False, 'error': 'Species is required'}), 400
            
            c.execute('''
                UPDATE fish_inventory 
                SET species = ?, common_name = ?, quantity = ?, notes = ?
                WHERE id = ?
            ''', (
                data.get('species'),
                data.get('common_name'),
                data.get('quantity', 1),
                data.get('notes'),
                fish_id
            ))
            conn.commit()
            return jsonify({'success': True})
        
        elif request.method == 'DELETE':
            fish_id = request.args.get('id', type=int)
            c.execute('DELETE FROM fish_inventory WHERE id = ?', (fish_id,))
            conn.commit()
            return jsonify({'success': True})
        
        else:
            c.execute('SELECT * FROM fish_inventory ORDER BY added_date DESC')
            rows = c.fetchall()
            return jsonify([dict(row) for row in rows])
    
    finally:
        conn.close()

@app.route('/api/stats')
def stats():
    """Get summary statistics"""
    conn = get_db()
    
    try:
        c = conn.cursor()
        
        # Latest parameters
        c.execute('SELECT * FROM water_parameters ORDER BY timestamp DESC LIMIT 1')
        latest_params = c.fetchone()
        
        # Upcoming tasks
        c.execute('''
            SELECT COUNT(*) as count FROM scheduled_tasks 
            WHERE active = 1 AND next_due <= datetime('now', '+7 days')
        ''')
        upcoming_tasks = c.fetchone()['count']
        
        # Total fish
        c.execute('SELECT SUM(quantity) as total FROM fish_inventory')
        total_fish = c.fetchone()['total'] or 0
        
        # Recent maintenance count
        c.execute('''
            SELECT COUNT(*) as count FROM maintenance_log 
            WHERE timestamp >= datetime('now', '-30 days')
        ''')
        recent_maintenance = c.fetchone()['count']
        
        return jsonify({
            'latest_parameters': dict(latest_params) if latest_params else None,
            'upcoming_tasks': upcoming_tasks,
            'total_fish': total_fish,
            'recent_maintenance': recent_maintenance
        })
    
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    print("🚀 Starting WaterScribe Complete on port 5003...")
    print("📊 All features enabled: Charts, Edit, Mobile UI")
    print("🔗 Access: http://localhost:5003 or http://192.168.221.163:5003")
    app.run(host='0.0.0.0', port=5003, debug=False, threaded=True)
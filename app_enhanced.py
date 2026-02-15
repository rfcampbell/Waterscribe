#!/usr/bin/env python3
"""
Aquarium Tracker Application - Enhanced Version
A Flask-based web app for tracking aquarium maintenance and parameters
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

def get_db():
    """Get database connection with proper timeout"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def validate_parameters(data):
    """Validate water parameter data"""
    errors = []
    
    if data.get('temperature') is not None:
        try:
            temp = float(data['temperature'])
            if temp < 0 or temp > 100:
                errors.append("Temperature must be between 0-100°F")
        except (ValueError, TypeError):
            errors.append("Temperature must be a number")
    
    if data.get('ph') is not None:
        try:
            ph = float(data['ph'])
            if ph < 0 or ph > 14:
                errors.append("pH must be between 0-14")
        except (ValueError, TypeError):
            errors.append("pH must be a number")
    
    for param in ['ammonia', 'nitrite', 'nitrate']:
        if data.get(param) is not None:
            try:
                val = float(data[param])
                if val < 0:
                    errors.append(f"{param.title()} cannot be negative")
            except (ValueError, TypeError):
                errors.append(f"{param.title()} must be a number")
    
    return errors

# Routes
@app.route('/')
def index():
    """Serve the main application page"""
    return render_template('index_dev.html')

@app.route('/api/parameters', methods=['GET', 'POST', 'PUT', 'DELETE'])
def parameters():
    """Handle water parameter data"""
    conn = get_db()
    
    try:
        if request.method == 'POST':
            data = request.json
            
            # Validate input
            errors = validate_parameters(data)
            if errors:
                return jsonify({'success': False, 'errors': errors}), 400
            
            c = conn.cursor()
            # Use local time explicitly
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
            
            errors = validate_parameters(data)
            if errors:
                return jsonify({'success': False, 'errors': errors}), 400
            
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
            # Delete a specific parameter reading by ID
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
            dt = datetime.fromisoformat(row['timestamp'])
            chart_data['labels'].append(dt.strftime('%m/%d'))
            
            # Add data points (handle None values)
            for param in ['temperature', 'ph', 'ammonia', 'nitrite', 'nitrate']:
                value = row[param]
                chart_data['datasets'][param]['data'].append(value)
        
        return jsonify(chart_data)
    
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
        
        elif request.method == 'PUT':
            # Update maintenance entry
            data = request.json
            entry_id = data.get('id')
            
            if not entry_id:
                return jsonify({'success': False, 'error': 'ID required'}), 400
            
            c = conn.cursor()
            c.execute('''
                UPDATE maintenance_log 
                SET task_type = ?, description = ?
                WHERE id = ?
            ''', (
                data.get('task_type'),
                data.get('description'),
                entry_id
            ))
            conn.commit()
            return jsonify({'success': True})
        
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
                # Recurring task with frequency
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
                # One-time task with specific date
                if not data.get('specific_date') or data['specific_date'].strip() == '':
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
            task_id = c.lastrowid
            return jsonify({'success': True, 'id': task_id})
        
        elif request.method == 'PUT':
            # Complete a task and reschedule (or deactivate if one-time)
            data = request.json
            task_id = data['id']
            
            c.execute('SELECT frequency_days, is_recurring FROM scheduled_tasks WHERE id = ?', (task_id,))
            row = c.fetchone()
            
            if row:
                is_recurring = row['is_recurring']
                now = datetime.now()
                
                if is_recurring:
                    # Recurring task - reschedule
                    frequency = row['frequency_days']
                    next_due = now + timedelta(days=frequency)
                    
                    c.execute('''
                        UPDATE scheduled_tasks 
                        SET last_completed = ?, next_due = ?
                        WHERE id = ?
                    ''', (now.isoformat(), next_due.isoformat(), task_id))
                else:
                    # One-time task - mark as inactive
                    c.execute('''
                        UPDATE scheduled_tasks 
                        SET last_completed = ?, active = 0
                        WHERE id = ?
                    ''', (now.isoformat(), task_id))
                
                # Also log to maintenance
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
            # GET: return all active scheduled tasks
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
            fish_id = c.lastrowid
            return jsonify({'success': True, 'id': fish_id})
        
        elif request.method == 'PUT':
            # Update fish entry
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
    app.run(host='0.0.0.0', port=5000, debug=False)
"""
API routes - JSON API for charts and CRUD operations
All operations are scoped to the current user's aquariums
"""
from flask import jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app.api import bp
from app.models import db, Aquarium, WaterParameter, MaintenanceLog, ScheduledTask, FishInventory

def get_user_aquarium(aquarium_id):
    """Helper to get aquarium that belongs to current user"""
    return Aquarium.query.filter_by(id=aquarium_id, user_id=current_user.id).first()

# Water Parameters API
@bp.route('/aquarium/<int:aquarium_id>/parameters', methods=['GET', 'POST', 'DELETE'])
@login_required
def parameters(aquarium_id):
    """Handle water parameter data for a specific aquarium"""
    aquarium = get_user_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    if request.method == 'POST':
        data = request.json
        parameter = WaterParameter(
            aquarium_id=aquarium_id,
            timestamp=datetime.utcnow(),
            temperature=data.get('temperature'),
            ph=data.get('ph'),
            ammonia=data.get('ammonia'),
            nitrite=data.get('nitrite'),
            nitrate=data.get('nitrate'),
            notes=data.get('notes')
        )
        
        try:
            db.session.add(parameter)
            db.session.commit()
            return jsonify({'success': True, 'id': parameter.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    elif request.method == 'DELETE':
        param_id = request.args.get('id', type=int)
        if not param_id:
            return jsonify({'success': False, 'error': 'ID required'}), 400
        
        parameter = WaterParameter.query.filter_by(id=param_id, aquarium_id=aquarium_id).first()
        if not parameter:
            return jsonify({'success': False, 'error': 'Parameter not found'}), 404
        
        try:
            db.session.delete(parameter)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    else:  # GET
        limit = request.args.get('limit', 50, type=int)
        parameters = WaterParameter.query.filter_by(
            aquarium_id=aquarium_id
        ).order_by(WaterParameter.timestamp.desc()).limit(limit).all()
        
        return jsonify([param.to_dict() for param in parameters])

# Maintenance Log API
@bp.route('/aquarium/<int:aquarium_id>/maintenance', methods=['GET', 'POST', 'DELETE'])
@login_required
def maintenance(aquarium_id):
    """Handle maintenance log entries for a specific aquarium"""
    aquarium = get_user_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    if request.method == 'POST':
        data = request.json
        maintenance_entry = MaintenanceLog(
            aquarium_id=aquarium_id,
            timestamp=datetime.utcnow(),
            task_type=data.get('task_type'),
            description=data.get('description'),
            completed=data.get('completed', True)
        )
        
        try:
            db.session.add(maintenance_entry)
            db.session.commit()
            return jsonify({'success': True, 'id': maintenance_entry.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    elif request.method == 'DELETE':
        entry_id = request.args.get('id', type=int)
        if not entry_id:
            return jsonify({'success': False, 'error': 'ID required'}), 400
        
        entry = MaintenanceLog.query.filter_by(id=entry_id, aquarium_id=aquarium_id).first()
        if not entry:
            return jsonify({'success': False, 'error': 'Entry not found'}), 404
        
        try:
            db.session.delete(entry)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    else:  # GET
        limit = request.args.get('limit', 50, type=int)
        entries = MaintenanceLog.query.filter_by(
            aquarium_id=aquarium_id
        ).order_by(MaintenanceLog.timestamp.desc()).limit(limit).all()
        
        return jsonify([entry.to_dict() for entry in entries])

# Scheduled Tasks API
@bp.route('/aquarium/<int:aquarium_id>/scheduled', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def scheduled_tasks(aquarium_id):
    """Handle scheduled tasks for a specific aquarium"""
    aquarium = get_user_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    if request.method == 'POST':
        data = request.json
        is_recurring = data.get('is_recurring', True)
        
        if is_recurring:
            if not data.get('frequency_days'):
                return jsonify({'success': False, 'error': 'Frequency is required for recurring tasks'}), 400
            
            next_due = datetime.utcnow() + timedelta(days=data['frequency_days'])
            task = ScheduledTask(
                aquarium_id=aquarium_id,
                task_name=data['task_name'],
                frequency_days=data['frequency_days'],
                next_due=next_due,
                description=data.get('description'),
                active=True,
                is_recurring=True
            )
        else:
            if not data.get('specific_date'):
                return jsonify({'success': False, 'error': 'Date is required for one-time tasks'}), 400
            
            try:
                specific_date = datetime.fromisoformat(data['specific_date'])
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format'}), 400
            
            task = ScheduledTask(
                aquarium_id=aquarium_id,
                task_name=data['task_name'],
                next_due=specific_date,
                description=data.get('description'),
                active=True,
                is_recurring=False,
                specific_date=specific_date
            )
        
        try:
            db.session.add(task)
            db.session.commit()
            return jsonify({'success': True, 'id': task.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    elif request.method == 'PUT':
        data = request.json
        task_id = data.get('id')
        if not task_id:
            return jsonify({'success': False, 'error': 'Task ID required'}), 400
        
        task = ScheduledTask.query.filter_by(id=task_id, aquarium_id=aquarium_id).first()
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        
        now = datetime.utcnow()
        
        if task.is_recurring:
            # Reschedule recurring task
            next_due = now + timedelta(days=task.frequency_days)
            task.last_completed = now
            task.next_due = next_due
        else:
            # Deactivate one-time task
            task.last_completed = now
            task.active = False
        
        # Log completion
        maintenance_entry = MaintenanceLog(
            aquarium_id=aquarium_id,
            timestamp=now,
            task_type=task.task_name,
            description='Completed scheduled task',
            completed=True
        )
        
        try:
            db.session.add(maintenance_entry)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    elif request.method == 'DELETE':
        task_id = request.args.get('id', type=int)
        if not task_id:
            return jsonify({'success': False, 'error': 'ID required'}), 400
        
        task = ScheduledTask.query.filter_by(id=task_id, aquarium_id=aquarium_id).first()
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        
        try:
            db.session.delete(task)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    else:  # GET
        tasks = ScheduledTask.query.filter_by(
            aquarium_id=aquarium_id,
            active=True
        ).order_by(ScheduledTask.next_due).all()
        
        return jsonify([task.to_dict() for task in tasks])

# Fish Inventory API
@bp.route('/aquarium/<int:aquarium_id>/fish', methods=['GET', 'POST', 'DELETE'])
@login_required
def fish_inventory(aquarium_id):
    """Handle fish inventory for a specific aquarium"""
    aquarium = get_user_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    if request.method == 'POST':
        data = request.json
        fish = FishInventory(
            aquarium_id=aquarium_id,
            species=data['species'],
            common_name=data.get('common_name'),
            quantity=data.get('quantity', 1),
            notes=data.get('notes')
        )
        
        try:
            db.session.add(fish)
            db.session.commit()
            return jsonify({'success': True, 'id': fish.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    elif request.method == 'DELETE':
        fish_id = request.args.get('id', type=int)
        if not fish_id:
            return jsonify({'success': False, 'error': 'ID required'}), 400
        
        fish = FishInventory.query.filter_by(id=fish_id, aquarium_id=aquarium_id).first()
        if not fish:
            return jsonify({'success': False, 'error': 'Fish not found'}), 404
        
        try:
            db.session.delete(fish)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    else:  # GET
        fish_list = FishInventory.query.filter_by(
            aquarium_id=aquarium_id
        ).order_by(FishInventory.added_date.desc()).all()
        
        return jsonify([fish.to_dict() for fish in fish_list])

# Charts API
@bp.route('/aquarium/<int:aquarium_id>/parameters/chart')
@login_required
def parameters_chart(aquarium_id):
    """Get parameter data formatted for charts"""
    aquarium = get_user_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    days = request.args.get('days', 30, type=int)
    since_date = datetime.utcnow() - timedelta(days=days)
    
    parameters = WaterParameter.query.filter(
        WaterParameter.aquarium_id == aquarium_id,
        WaterParameter.timestamp >= since_date
    ).order_by(WaterParameter.timestamp.asc()).all()
    
    # Format data for Chart.js
    chart_data = {
        'labels': [],
        'datasets': {
            'temperature': {
                'label': 'Temperature (°F)',
                'data': [],
                'borderColor': '#ff6b9d',
                'backgroundColor': 'rgba(255, 107, 157, 0.1)',
                'yAxisID': 'y'
            },
            'ph': {
                'label': 'pH',
                'data': [],
                'borderColor': '#4ecdc4',
                'backgroundColor': 'rgba(78, 205, 196, 0.1)',
                'yAxisID': 'y1'
            },
            'ammonia': {
                'label': 'Ammonia (ppm)',
                'data': [],
                'borderColor': '#f7b267',
                'backgroundColor': 'rgba(247, 178, 103, 0.1)',
                'yAxisID': 'y1'
            },
            'nitrite': {
                'label': 'Nitrite (ppm)',
                'data': [],
                'borderColor': '#2d6a4f',
                'backgroundColor': 'rgba(45, 106, 79, 0.1)',
                'yAxisID': 'y1'
            },
            'nitrate': {
                'label': 'Nitrate (ppm)',
                'data': [],
                'borderColor': '#e0e040',
                'backgroundColor': 'rgba(224, 224, 64, 0.1)',
                'yAxisID': 'y1'
            }
        }
    }
    
    for param in parameters:
        chart_data['labels'].append(param.timestamp.strftime('%m/%d'))
        
        for field in ['temperature', 'ph', 'ammonia', 'nitrite', 'nitrate']:
            value = getattr(param, field)
            chart_data['datasets'][field]['data'].append(
                float(value) if value is not None else None
            )
    
    return jsonify(chart_data)

# Stats API
@bp.route('/aquarium/<int:aquarium_id>/stats')
@login_required
def aquarium_stats(aquarium_id):
    """Get summary statistics for an aquarium"""
    aquarium = get_user_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    # Latest parameters
    latest_params = WaterParameter.query.filter_by(
        aquarium_id=aquarium_id
    ).order_by(WaterParameter.timestamp.desc()).first()
    
    # Upcoming tasks
    upcoming_tasks = ScheduledTask.query.filter(
        ScheduledTask.aquarium_id == aquarium_id,
        ScheduledTask.active == True,
        ScheduledTask.next_due <= datetime.utcnow() + timedelta(days=7)
    ).count()
    
    # Total fish
    total_fish = db.session.query(db.func.sum(FishInventory.quantity)).filter_by(
        aquarium_id=aquarium_id
    ).scalar() or 0
    
    # Recent maintenance count
    recent_maintenance = MaintenanceLog.query.filter(
        MaintenanceLog.aquarium_id == aquarium_id,
        MaintenanceLog.timestamp >= datetime.utcnow() - timedelta(days=30)
    ).count()
    
    return jsonify({
        'latest_parameters': latest_params.to_dict() if latest_params else None,
        'upcoming_tasks': upcoming_tasks,
        'total_fish': total_fish,
        'recent_maintenance': recent_maintenance
    })
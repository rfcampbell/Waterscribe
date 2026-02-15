"""
Dashboard routes - main UI and aquarium management
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.dashboard import bp
from app.models import db, Aquarium, WaterParameter, MaintenanceLog, ScheduledTask, FishInventory

@bp.route('/')
@login_required
def index():
    """Main dashboard - shows aquarium selector and dashboard"""
    # Get user's aquariums
    aquariums = Aquarium.query.filter_by(user_id=current_user.id).order_by(Aquarium.name).all()
    
    # If no aquariums, redirect to create one
    if not aquariums:
        flash('Welcome! Let\'s set up your first aquarium.', 'info')
        return redirect(url_for('dashboard.create_aquarium'))
    
    # Get the selected aquarium (default to first one)
    selected_id = request.args.get('aquarium_id', type=int)
    if selected_id:
        selected_aquarium = Aquarium.query.filter_by(id=selected_id, user_id=current_user.id).first()
        if not selected_aquarium:
            selected_aquarium = aquariums[0]
    else:
        selected_aquarium = aquariums[0]
    
    # Get recent data for the selected aquarium
    recent_parameters = WaterParameter.query.filter_by(
        aquarium_id=selected_aquarium.id
    ).order_by(WaterParameter.timestamp.desc()).limit(10).all()
    
    upcoming_tasks = ScheduledTask.query.filter_by(
        aquarium_id=selected_aquarium.id,
        active=True
    ).order_by(ScheduledTask.next_due).limit(5).all()
    
    recent_maintenance = MaintenanceLog.query.filter_by(
        aquarium_id=selected_aquarium.id
    ).order_by(MaintenanceLog.timestamp.desc()).limit(10).all()
    
    fish_count = db.session.query(db.func.sum(FishInventory.quantity)).filter_by(
        aquarium_id=selected_aquarium.id
    ).scalar() or 0
    
    return render_template('dashboard/index.html',
                         aquariums=aquariums,
                         selected_aquarium=selected_aquarium,
                         recent_parameters=recent_parameters,
                         upcoming_tasks=upcoming_tasks,
                         recent_maintenance=recent_maintenance,
                         fish_count=fish_count)

@bp.route('/aquarium/<int:aquarium_id>')
@login_required
def aquarium_detail(aquarium_id):
    """Single aquarium view with all tabs"""
    aquarium = Aquarium.query.filter_by(id=aquarium_id, user_id=current_user.id).first_or_404()
    
    return render_template('dashboard/aquarium.html', aquarium=aquarium)

@bp.route('/create-aquarium', methods=['GET', 'POST'])
@login_required
def create_aquarium():
    """Create a new aquarium"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        aquarium = Aquarium(
            user_id=current_user.id,
            name=data.get('name'),
            type=data.get('type'),
            volume_gallons=float(data.get('volume_gallons')) if data.get('volume_gallons') else None,
            description=data.get('description')
        )
        
        try:
            db.session.add(aquarium)
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'id': aquarium.id})
            else:
                flash(f'Aquarium "{aquarium.name}" created successfully!', 'success')
                return redirect(url_for('dashboard.index', aquarium_id=aquarium.id))
        
        except Exception as e:
            db.session.rollback()
            if request.is_json:
                return jsonify({'success': False, 'error': str(e)}), 400
            else:
                flash('Failed to create aquarium. Please try again.', 'danger')
    
    return render_template('dashboard/create_aquarium.html')

@bp.route('/aquarium/<int:aquarium_id>/edit', methods=['POST'])
@login_required
def edit_aquarium(aquarium_id):
    """Edit an existing aquarium"""
    aquarium = Aquarium.query.filter_by(id=aquarium_id, user_id=current_user.id).first_or_404()
    
    data = request.get_json() if request.is_json else request.form
    
    aquarium.name = data.get('name', aquarium.name)
    aquarium.type = data.get('type', aquarium.type)
    aquarium.volume_gallons = float(data.get('volume_gallons')) if data.get('volume_gallons') else aquarium.volume_gallons
    aquarium.description = data.get('description', aquarium.description)
    
    try:
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True})
        else:
            flash('Aquarium updated successfully!', 'success')
            return redirect(url_for('dashboard.index', aquarium_id=aquarium_id))
    
    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        else:
            flash('Failed to update aquarium.', 'danger')
            return redirect(url_for('dashboard.index', aquarium_id=aquarium_id))

@bp.route('/aquarium/<int:aquarium_id>/delete', methods=['POST'])
@login_required
def delete_aquarium(aquarium_id):
    """Delete an aquarium and all its data"""
    aquarium = Aquarium.query.filter_by(id=aquarium_id, user_id=current_user.id).first_or_404()
    
    try:
        db.session.delete(aquarium)
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True})
        else:
            flash(f'Aquarium "{aquarium.name}" deleted successfully.', 'success')
            return redirect(url_for('dashboard.index'))
    
    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        else:
            flash('Failed to delete aquarium.', 'danger')
            return redirect(url_for('dashboard.index'))
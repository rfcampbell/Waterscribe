"""
Dashboard routes - main UI and aquarium management
"""
from app.utils import parse_number
from flask import render_template, redirect, url_for, flash, request, jsonify

from app.dashboard import bp
from app.models import db, Aquarium, Reading, Event, ScheduledTask, FishInventory
from app.catalog import PARAMETERS, EVENT_TYPES, QUALITIES
from app.api.routes import latest_readings

@bp.route('/')
def index():
    """Main dashboard - shows aquarium selector and dashboard"""
    # Get user's aquariums
    aquariums = Aquarium.query.order_by(Aquarium.name).all()
    
    # If no aquariums, send them to the manage page to add one
    if not aquariums:
        flash('Welcome! Let\'s set up your first aquarium.', 'info')
        return redirect(url_for('dashboard.manage_aquariums'))
    
    # Get the selected aquarium (default to first one)
    selected_id = request.args.get('aquarium_id', type=int)
    if selected_id:
        selected_aquarium = db.session.get(Aquarium, selected_id)
        if not selected_aquarium:
            selected_aquarium = aquariums[0]
    else:
        selected_aquarium = aquariums[0]
    
    latest = latest_readings(selected_aquarium.id)
    # Methods used before, newest first per parameter -- the entry form suggests and pre-fills them
    methods = {}
    for param, method in db.session.query(Reading.parameter, Reading.method).filter(
            Reading.method.isnot(None)).order_by(Reading.timestamp.desc()):
        methods.setdefault(param, [])
        if method not in methods[param]:
            methods[param].append(method)
    last_bubble = Event.query.filter_by(aquarium_id=selected_aquarium.id, event_type='co2_bubble_rate'
                                        ).filter(Event.value.isnot(None)).order_by(Event.timestamp.desc()).first()
    
    upcoming_tasks = ScheduledTask.query.filter_by(
        aquarium_id=selected_aquarium.id,
        active=True
    ).order_by(ScheduledTask.next_due).limit(5).all()
    
    fish_held = db.session.query(db.func.sum(FishInventory.held)).filter_by(
        aquarium_id=selected_aquarium.id
    ).scalar() or 0
    fish_planned = db.session.query(db.func.sum(FishInventory.planned)).filter_by(
        aquarium_id=selected_aquarium.id
    ).scalar() or 0
    
    return render_template('dashboard/index.html',
                         aquariums=aquariums,
                         selected_aquarium=selected_aquarium,
                         latest=latest,
                         latest_json={k: r.to_dict() for k, r in latest.items()},
                         last_bubble=last_bubble,
                         methods=methods,
                         parameters=PARAMETERS,
                         event_types=EVENT_TYPES,
                         qualities=QUALITIES,
                         upcoming_tasks=upcoming_tasks,
                         fish_held=fish_held,
                         fish_planned=fish_planned)

@bp.route('/aquarium/<int:aquarium_id>')
def aquarium_detail(aquarium_id):
    """Single aquarium view with all tabs"""
    aquarium = db.get_or_404(Aquarium, aquarium_id)
    
    return render_template('dashboard/aquarium.html', aquarium=aquarium)

@bp.route('/create-aquarium', methods=['GET', 'POST'])
def create_aquarium():
    """Create a new aquarium"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        try:
            volume = parse_number(data.get('volume_gallons'), minimum=0)
        except ValueError:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Volume must be a number'}), 400
            flash('Volume must be a number.', 'danger')
            return redirect(url_for('dashboard.manage_aquariums'))
        
        name = (data.get('name') or '').strip()
        if not name:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Name is required'}), 400
            flash('Name is required.', 'danger')
            return redirect(url_for('dashboard.manage_aquariums'))
        
        aquarium = Aquarium(
            name=name,
            type=(data.get('type') or '').strip() or None,
            volume_gallons=volume,
            description=(data.get('description') or '').strip() or None
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
    
    return redirect(url_for('dashboard.manage_aquariums'))

@bp.route('/aquariums')
def manage_aquariums():
    """List all aquariums with edit/delete"""
    aquariums = Aquarium.query.order_by(Aquarium.name).all()
    counts = {}
    for a in aquariums:
        counts[a.id] = {
            'readings': Reading.query.filter_by(aquarium_id=a.id).count(),
            'events': Event.query.filter_by(aquarium_id=a.id).count(),
            'tasks': ScheduledTask.query.filter_by(aquarium_id=a.id).count(),
            'fish': FishInventory.query.filter_by(aquarium_id=a.id).count(),
        }
    return render_template('dashboard/manage.html', title='Manage Aquariums',
                           aquariums=aquariums, counts=counts)

@bp.route('/aquarium/<int:aquarium_id>/edit', methods=['POST'])
def edit_aquarium(aquarium_id):
    """Edit an existing aquarium"""
    aquarium = db.get_or_404(Aquarium, aquarium_id)
    
    data = request.get_json() if request.is_json else request.form
    
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Name is required'}), 400
            flash('Name is required.', 'danger')
            return redirect(url_for('dashboard.manage_aquariums'))
        aquarium.name = name
    if 'type' in data:
        aquarium.type = (data.get('type') or '').strip() or None
    if 'volume_gallons' in data:
        try:
            aquarium.volume_gallons = parse_number(data.get('volume_gallons'), minimum=0)
        except ValueError:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Volume must be a number'}), 400
            flash('Volume must be a number.', 'danger')
            return redirect(url_for('dashboard.manage_aquariums'))
    if 'description' in data:
        aquarium.description = (data.get('description') or '').strip() or None
    
    try:
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True})
        else:
            flash(f'Aquarium "{aquarium.name}" updated.', 'success')
            return redirect(url_for('dashboard.manage_aquariums'))
    
    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        else:
            flash('Failed to update aquarium.', 'danger')
            return redirect(url_for('dashboard.manage_aquariums'))

@bp.route('/aquarium/<int:aquarium_id>/delete', methods=['POST'])
def delete_aquarium(aquarium_id):
    """Delete an aquarium and all its data"""
    aquarium = db.get_or_404(Aquarium, aquarium_id)
    
    try:
        db.session.delete(aquarium)
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True})
        else:
            flash(f'Aquarium "{aquarium.name}" deleted.', 'success')
            return redirect(url_for('dashboard.manage_aquariums'))
    
    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        else:
            flash('Failed to delete aquarium.', 'danger')
            return redirect(url_for('dashboard.manage_aquariums'))
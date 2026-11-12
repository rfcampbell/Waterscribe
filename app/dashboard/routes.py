"""
Dashboard routes - main UI and aquarium management
"""
import re
from datetime import datetime
from app.utils import parse_number
from flask import render_template, redirect, url_for, flash, request, jsonify, make_response

from app.dashboard import bp
from app.models import db, Aquarium, Reading, Event, ScheduledTask, FishInventory
from app.catalog import PARAMETERS, EVENT_TYPES, QUALITIES, TARGET_KEYS, TARGET_RANGES
from app.api.routes import latest_readings
from app.overview import build_tiles, fmt_target
from app.targets import save_targets, targets_for

TANK_COOKIE = 'ws_tank'

def ordered_aquariums():
    return Aquarium.query.order_by(Aquarium.sort_order, Aquarium.code).all()

@bp.route('/')
def index():
    """Main dashboard - shows aquarium selector and dashboard"""
    # Get user's aquariums
    aquariums = ordered_aquariums()
    
    # If no aquariums, send them to the manage page to add one
    if not aquariums:
        flash('Welcome! Let\'s set up your first aquarium.', 'info')
        return redirect(url_for('dashboard.manage_aquariums'))
    
    # Selected tank: ?aquarium_id=, else the last one picked (cookie), else the first
    selected_id = request.args.get('aquarium_id', type=int) or request.cookies.get(TANK_COOKIE, type=int)
    selected_aquarium = next((a for a in aquariums if a.id == selected_id), aquariums[0])
    
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
    
    targets = targets_for(selected_aquarium.id)
    tiles = build_tiles(Reading.query.filter_by(aquarium_id=selected_aquarium.id).all(), targets,
                        datetime.now())
    if last_bubble:
        from app.overview import age_text
        last_bubble_age = age_text(last_bubble.timestamp, last_bubble.time_known, datetime.now())
    else:
        last_bubble_age = None
    next_task = next((t for t in upcoming_tasks if t.next_due), upcoming_tasks[0] if upcoming_tasks else None)

    resp = make_response(render_template('dashboard/index.html',
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
                         fish_planned=fish_planned,
                         tiles=tiles,
                         fmt_target=fmt_target,
                         last_bubble_age=last_bubble_age,
                         next_task=next_task))
    resp.set_cookie(TANK_COOKIE, str(selected_aquarium.id), max_age=365 * 86400, samesite='Lax')
    return resp

@bp.route('/aquarium/<int:aquarium_id>')
def aquarium_detail(aquarium_id):
    """Single aquarium view with all tabs"""
    aquarium = db.get_or_404(Aquarium, aquarium_id)
    
    return render_template('dashboard/aquarium.html', aquarium=aquarium)

CODE_RE = re.compile(r'^[A-Z0-9_-]{1,10}$')

def parse_code(raw, aquarium_id=None):
    """'100p ' -> '100P'. Required: every tank needs a code (CSV import and the MCP server name
    tanks by it). Raises ValueError if blank, malformed or taken by another tank."""
    code = (raw or '').strip().upper()
    if not code:
        raise ValueError('Code is required (1-10 letters, digits, - or _, e.g. 100P)')
    if not CODE_RE.match(code):
        raise ValueError('Code must be 1-10 letters, digits, - or _ (e.g. 100P)')
    taken = Aquarium.query.filter(Aquarium.code == code, Aquarium.id != aquarium_id).first()
    if taken:
        raise ValueError(f'Code {code} is already used by {taken.name}')
    return code

def _bad(msg, redirect_to='dashboard.manage_aquariums'):
    if request.is_json:
        return jsonify({'success': False, 'error': msg}), 400
    flash(msg, 'danger')
    return redirect(url_for(redirect_to))

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
        
        try:
            code = parse_code(data.get('code'))
        except ValueError as e:
            return _bad(str(e))
        
        last = db.session.query(db.func.max(Aquarium.sort_order)).scalar() or 0
        aquarium = Aquarium(
            sort_order=last + 1,
            name=name,
            code=code,
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
    aquariums = ordered_aquariums()
    counts = {}
    for a in aquariums:
        counts[a.id] = {
            'readings': Reading.query.filter_by(aquarium_id=a.id).count(),
            'events': Event.query.filter_by(aquarium_id=a.id).count(),
            'tasks': ScheduledTask.query.filter_by(aquarium_id=a.id).count(),
            'fish': FishInventory.query.filter_by(aquarium_id=a.id).count(),
        }
    targets = {a.id: targets_for(a.id) for a in aquariums}
    return render_template('dashboard/manage.html', title='Manage Aquariums',
                           aquariums=aquariums, counts=counts, targets=targets,
                           target_keys=TARGET_KEYS, target_ranges=TARGET_RANGES, fmt_target=fmt_target)

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
    if 'code' in data:     # absent = unchanged; present but blank is rejected
        try:
            aquarium.code = parse_code(data.get('code'), aquarium.id)
        except ValueError as e:
            return _bad(str(e))
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
    if 'sort_order' in data:
        try:
            aquarium.sort_order = parse_number(data.get('sort_order'), cast=int, default=aquarium.sort_order)
        except ValueError:
            return _bad('Order must be a whole number')
    
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

@bp.route('/aquarium/<int:aquarium_id>/targets', methods=['POST'])
def edit_targets(aquarium_id):
    """Save target ranges. JSON: {"targets": {key: {"min": .., "max": ..}}}; form: min_<key>, max_<key>.
    Keys left out are unchanged; both ends blank removes a target. All-or-nothing."""
    aquarium = db.get_or_404(Aquarium, aquarium_id)
    if request.is_json:
        raw = (request.get_json(silent=True) or {}).get('targets')
        if not isinstance(raw, dict) or not all(isinstance(v, dict) for v in raw.values()):
            return _bad('targets must be an object of {min, max}')
        data = {k: (v.get('min'), v.get('max')) for k, v in raw.items()}
    else:
        keys = {f[4:] for f in request.form if f[:4] in ('min_', 'max_')}
        data = {k: (request.form.get('min_' + k), request.form.get('max_' + k)) for k in keys}
    try:
        save_targets(aquarium, data)
    except ValueError as e:
        db.session.rollback()
        return _bad(f'{aquarium.code}: {e}')
    if request.is_json:
        return jsonify({'success': True, 'targets': {k: {'min': lo, 'max': hi}
                                                     for k, (lo, hi) in targets_for(aquarium.id).items()}})
    flash(f'Targets for {aquarium.code} saved.', 'success')
    return redirect(url_for('dashboard.manage_aquariums') + f'#tank-{aquarium.id}')

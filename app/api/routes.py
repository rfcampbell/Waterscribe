"""
API routes - JSON API for charts and CRUD operations
"""
import json
from flask import jsonify, request, Response
from datetime import datetime, timedelta

from app.api import bp
from app.models import db, Aquarium, Reading, Event, ScheduledTask, FishInventory
from app.notifications import notify_task_created
from app.fish_images import fetch_fish_image, fetch_species_info
from app.utils import parse_number
from app.catalog import PARAMETERS, EVENT_TYPES, CHART_GROUPS, QUALITIES, UNIT_CONVERSIONS
from app.records import (clean_reading, clean_event, when_from_json, readings_csv, events_csv,
                         apply_reading_unit, check_event_unit)

def get_aquarium(aquarium_id):
    return db.session.get(Aquarium, aquarium_id)

def _err(msg, code=400):
    return jsonify({'success': False, 'error': msg}), code

def _commit(**extra):
    try:
        db.session.commit()
        return jsonify({'success': True, **extra})
    except Exception as e:
        db.session.rollback()
        return _err(str(e))

def _since():
    """?days=N limits to the last N days; absent or 0 means everything."""
    days = request.args.get('days', 0, type=int)
    return datetime.now() - timedelta(days=days) if days > 0 else None

# Tanks and catalog (read-only; used by the MCP server so it never hard-codes names or units)
@bp.route('/aquariums')
def list_aquariums():
    return jsonify([{'id': a.id, 'code': a.code, 'name': a.name.strip(), 'type': a.type,
                     'volume_gallons': a.volume_gallons, 'description': a.description}
                    for a in Aquarium.query.order_by(Aquarium.code, Aquarium.name).all()])

@bp.route('/catalog')
def catalog():
    return jsonify({
        'parameters': [{'key': k, 'label': p[0], 'unit': p[1],
                        'also_accepts': [u for (pk, u) in UNIT_CONVERSIONS if pk == k]}
                       for k, p in PARAMETERS.items()],
        'event_types': [{'key': k, 'label': e[0], 'unit': e[1]} for k, e in EVENT_TYPES.items()],
        'qualities': list(QUALITIES),
    })

# Readings API
@bp.route('/aquarium/<int:aquarium_id>/readings', methods=['GET', 'POST', 'PUT', 'DELETE'])
def readings(aquarium_id):
    """GET list; POST {date, time, readings: [...]} adds several taken together;
    PUT {id, date, time, ...} edits one; DELETE ?id= removes one."""
    if not get_aquarium(aquarium_id):
        return _err('Aquarium not found', 404)
    data = request.get_json(silent=True) or {}

    if request.method == 'POST':
        rows = [r for r in data.get('readings', []) if str(r.get('value', '')).strip() != '']
        if not rows:
            return _err('Enter at least one reading')
        try:
            batch_when = when_from_json(data)
            # a row may carry its own date/time; otherwise it shares the batch's
            cleaned = [(when_from_json(r) if r.get('date') else batch_when,
                        apply_reading_unit(clean_reading(r), r.get('unit'))) for r in rows]
        except ValueError as e:
            return _err(str(e))
        added = [Reading(aquarium_id=aquarium_id, timestamp=ts, time_known=known, **c) for (ts, known), c in cleaned]
        db.session.add_all(added)
        db.session.flush()
        # echo what was stored (after unit conversion), not what was sent
        return _commit(count=len(added), readings=[r.to_dict() for r in added])

    if request.method == 'PUT':
        reading = Reading.query.filter_by(id=data.get('id'), aquarium_id=aquarium_id).first()
        if not reading:
            return _err('Reading not found', 404)
        try:
            ts, known = when_from_json(data)
            cleaned = clean_reading(data)
        except ValueError as e:
            return _err(str(e))
        reading.timestamp, reading.time_known = ts, known
        for k, v in cleaned.items():
            setattr(reading, k, v)
        return _commit(id=reading.id)

    if request.method == 'DELETE':
        reading = Reading.query.filter_by(id=request.args.get('id', type=int), aquarium_id=aquarium_id).first()
        if not reading:
            return _err('Reading not found', 404)
        db.session.delete(reading)
        return _commit()

    q = Reading.query.filter_by(aquarium_id=aquarium_id)
    if request.args.get('parameter'):
        q = q.filter_by(parameter=request.args['parameter'])
    since = _since()
    if since:
        q = q.filter(Reading.timestamp >= since)
    q = q.order_by(Reading.timestamp.desc(), Reading.id.desc())
    limit = request.args.get('limit', type=int)
    if limit:
        q = q.limit(limit)
    return jsonify([r.to_dict() for r in q.all()])

# Events API
@bp.route('/aquarium/<int:aquarium_id>/events', methods=['GET', 'POST', 'PUT', 'DELETE'])
def events(aquarium_id):
    if not get_aquarium(aquarium_id):
        return _err('Aquarium not found', 404)
    data = request.get_json(silent=True) or {}

    if request.method in ('POST', 'PUT'):
        try:
            ts, known = when_from_json(data)
            cleaned = check_event_unit(clean_event(data), data.get('unit'))
        except ValueError as e:
            return _err(str(e))
        if request.method == 'POST':
            event = Event(aquarium_id=aquarium_id)
            db.session.add(event)
        else:
            event = Event.query.filter_by(id=data.get('id'), aquarium_id=aquarium_id).first()
            if not event:
                return _err('Event not found', 404)
        event.timestamp, event.time_known = ts, known
        for k, v in cleaned.items():
            setattr(event, k, v)
        db.session.flush()
        return _commit(id=event.id)

    if request.method == 'DELETE':
        event = Event.query.filter_by(id=request.args.get('id', type=int), aquarium_id=aquarium_id).first()
        if not event:
            return _err('Event not found', 404)
        db.session.delete(event)
        return _commit()

    q = Event.query.filter_by(aquarium_id=aquarium_id)
    since = _since()
    if since:
        q = q.filter(Event.timestamp >= since)
    q = q.order_by(Event.timestamp.desc(), Event.id.desc())
    limit = request.args.get('limit', type=int)
    if limit:
        q = q.limit(limit)
    return jsonify([e.to_dict() for e in q.all()])

# CSV export (same format import_csv.py reads)
@bp.route('/aquarium/<int:aquarium_id>/readings.csv')
def export_readings(aquarium_id):
    aquarium = get_aquarium(aquarium_id)
    if not aquarium:
        return _err('Aquarium not found', 404)
    rows = Reading.query.filter_by(aquarium_id=aquarium_id).order_by(Reading.timestamp, Reading.id).all()
    return _csv(readings_csv(rows, aquarium.name), f'{aquarium.name}_readings.csv')

@bp.route('/aquarium/<int:aquarium_id>/events.csv')
def export_events(aquarium_id):
    aquarium = get_aquarium(aquarium_id)
    if not aquarium:
        return _err('Aquarium not found', 404)
    rows = Event.query.filter_by(aquarium_id=aquarium_id).order_by(Event.timestamp, Event.id).all()
    return _csv(events_csv(rows, aquarium.name), f'{aquarium.name}_events.csv')

def _csv(text, filename):
    safe = ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)
    return Response(text, mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{safe}"'})

# Scheduled Tasks API
@bp.route('/aquarium/<int:aquarium_id>/scheduled', methods=['GET', 'POST', 'PUT', 'DELETE'])
def scheduled_tasks(aquarium_id):
    """Handle scheduled tasks for a specific aquarium"""
    aquarium = get_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    if request.method == 'POST':
        data = request.json
        is_recurring = data.get('is_recurring', True)
        
        if is_recurring:
            try:
                frequency_days = parse_number(data.get('frequency_days'), int, minimum=1)
            except ValueError:
                return jsonify({'success': False, 'error': 'Frequency must be a whole number of days'}), 400
            if not frequency_days:
                return jsonify({'success': False, 'error': 'Frequency is required for recurring tasks'}), 400
            
            next_due = datetime.utcnow() + timedelta(days=frequency_days)
            task = ScheduledTask(
                aquarium_id=aquarium_id,
                task_name=data['task_name'],
                frequency_days=frequency_days,
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
            # Send Slack notification
            try:
                notify_task_created(task, aquarium.name)
            except Exception:
                pass  # Don't fail the request if notification fails
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
        completion = Event(
            aquarium_id=aquarium_id,
            event_type='task_completed',
            notes=task.task_name,
        )
        
        try:
            db.session.add(completion)
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
@bp.route('/aquarium/<int:aquarium_id>/fish', methods=['GET', 'POST', 'PUT', 'DELETE'])
def fish_inventory(aquarium_id):
    """Handle fish inventory for a specific aquarium"""
    aquarium = get_aquarium(aquarium_id)
    if not aquarium:
        return jsonify({'success': False, 'error': 'Aquarium not found'}), 404
    
    if request.method == 'POST':
        data = request.json
        try:
            held = parse_number(data.get('held'), int, default=0, minimum=0)
            planned = parse_number(data.get('planned'), int, default=0, minimum=0)
        except ValueError:
            return jsonify({'success': False, 'error': 'Held and planned must be whole numbers'}), 400
        # Fetch thumbnail from Wikipedia
        image_url = None
        try:
            image_url = fetch_fish_image(data['species'], data.get('common_name'))
        except Exception:
            pass
        
        # Fetch species info from Wikipedia
        species_info = None
        try:
            info = fetch_species_info(data['species'], data.get('common_name'))
            if info:
                species_info = json.dumps(info)
        except Exception:
            pass
        
        fish = FishInventory(
            aquarium_id=aquarium_id,
            species=data['species'],
            common_name=data.get('common_name'),
            held=held,
            planned=planned,
            notes=data.get('notes'),
            image_url=image_url,
            species_info=species_info
        )
        
        try:
            db.session.add(fish)
            db.session.commit()
            return jsonify({'success': True, 'id': fish.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    
    elif request.method == 'PUT':
        data = request.json
        fish_id = data.get('id')
        if not fish_id:
            return jsonify({'success': False, 'error': 'Fish ID required'}), 400
        
        fish = FishInventory.query.filter_by(id=fish_id, aquarium_id=aquarium_id).first()
        if not fish:
            return jsonify({'success': False, 'error': 'Fish not found'}), 404
        
        try:
            if 'held' in data:
                fish.held = parse_number(data['held'], int, default=0, minimum=0)
            if 'planned' in data:
                fish.planned = parse_number(data['planned'], int, default=0, minimum=0)
        except ValueError:
            return jsonify({'success': False, 'error': 'Held and planned must be whole numbers'}), 400
        if 'species' in data:
            fish.species = data['species']
        if 'common_name' in data:
            fish.common_name = data['common_name']
        if 'notes' in data:
            fish.notes = data['notes']
        
        try:
            db.session.commit()
            return jsonify({'success': True})
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
@bp.route('/aquarium/<int:aquarium_id>/chart')
def chart_data(aquarium_id):
    """Series per chart group. 'bad' readings are left out; 'suspect' are flagged
    per point. Includes water changes (vertical markers) and CO2 bubble rate."""
    if not get_aquarium(aquarium_id):
        return _err('Aquarium not found', 404)
    since = _since()

    q = Reading.query.filter(Reading.aquarium_id == aquarium_id, Reading.quality != 'bad')
    if since:
        q = q.filter(Reading.timestamp >= since)
    groups = {}
    for r in q.order_by(Reading.timestamp).all():
        if r.parameter not in PARAMETERS:
            continue
        label, unit, _, group = PARAMETERS[r.parameter]
        g = groups.setdefault(group, {'key': group, 'title': CHART_GROUPS.get(group, label), 'series': {}})
        s = g['series'].setdefault(r.parameter, {'parameter': r.parameter, 'label': label, 'unit': unit, 'points': []})
        s['points'].append({'t': r.timestamp.isoformat(timespec='minutes'), 'time_known': r.time_known,
                            'y': r.value, 'min': r.value_min, 'max': r.value_max,
                            'method': r.method, 'quality': r.quality, 'notes': r.notes})

    eq = Event.query.filter(Event.aquarium_id == aquarium_id,
                            Event.event_type.in_(('water_change', 'co2_bubble_rate')))
    if since:
        eq = eq.filter(Event.timestamp >= since)
    evs = eq.order_by(Event.timestamp).all()
    co2 = [e for e in evs if e.event_type == 'co2_bubble_rate' and e.value is not None]
    if since:
        # last bubble-rate setting before the window, so the step line starts at the left edge
        prior = Event.query.filter(Event.aquarium_id == aquarium_id, Event.event_type == 'co2_bubble_rate',
                                   Event.value.isnot(None), Event.timestamp < since
                                   ).order_by(Event.timestamp.desc()).first()
        if prior:
            co2.insert(0, prior)

    order = list(CHART_GROUPS)
    return jsonify({
        'groups': sorted(groups.values(), key=lambda g: order.index(g['key']) if g['key'] in order else 99),
        'water_changes': [{'t': e.timestamp.isoformat(timespec='minutes'), 'value': e.value, 'notes': e.notes}
                          for e in evs if e.event_type == 'water_change'],
        'co2_bubble_rate': [{'t': e.timestamp.isoformat(timespec='minutes'), 'y': e.value, 'notes': e.notes}
                            for e in co2],
    })

def latest_readings(aquarium_id):
    """Most recent non-bad reading per parameter: {parameter: Reading}."""
    sub = db.session.query(Reading.parameter, db.func.max(Reading.timestamp).label('ts')).filter(
        Reading.aquarium_id == aquarium_id, Reading.quality != 'bad').group_by(Reading.parameter).subquery()
    rows = Reading.query.join(sub, db.and_(Reading.parameter == sub.c.parameter, Reading.timestamp == sub.c.ts)
                              ).filter(Reading.aquarium_id == aquarium_id, Reading.quality != 'bad'
                              ).order_by(Reading.id).all()
    return {r.parameter: r for r in rows}

# Stats API
@bp.route('/aquarium/<int:aquarium_id>/stats')
def aquarium_stats(aquarium_id):
    """Get summary statistics for an aquarium"""
    if not get_aquarium(aquarium_id):
        return _err('Aquarium not found', 404)
    upcoming_tasks = ScheduledTask.query.filter(
        ScheduledTask.aquarium_id == aquarium_id,
        ScheduledTask.active == True,
        ScheduledTask.next_due <= datetime.utcnow() + timedelta(days=7)
    ).count()
    total_fish = db.session.query(db.func.sum(FishInventory.held)).filter_by(
        aquarium_id=aquarium_id
    ).scalar() or 0
    recent_events = Event.query.filter(
        Event.aquarium_id == aquarium_id,
        Event.timestamp >= datetime.now() - timedelta(days=30)
    ).count()
    return jsonify({
        'latest_readings': {k: r.to_dict() for k, r in latest_readings(aquarium_id).items()},
        'upcoming_tasks': upcoming_tasks,
        'total_fish': total_fish,
        'recent_events': recent_events,
    })

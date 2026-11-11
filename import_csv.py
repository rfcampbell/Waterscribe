#!/usr/bin/env python3
"""
Import readings or events from CSV (the format the app exports).

    venv/bin/python import_csv.py FILE.csv [--aquarium NAME] [--dry-run]

The kind (readings/events) is detected from the header. The tank column picks
the aquarium (case-insensitive name match) unless --aquarium is given. Every
row is validated before anything is written; any error aborts the whole file.
Rows identical to ones already stored are skipped, so re-running is safe.
"""
import argparse
import csv
import sys

from dotenv import load_dotenv
load_dotenv()

from wsgi import app
from app.models import db, Aquarium, Reading, Event
from app.records import READING_COLUMNS, EVENT_COLUMNS, reading_from_csv_row, event_from_csv_row


def find_aquarium(name):
    matches = Aquarium.query.filter(db.func.lower(db.func.trim(Aquarium.name)) == name.strip().lower()).all()
    if len(matches) != 1:
        names = ', '.join(a.name.strip() for a in Aquarium.query.order_by(Aquarium.name))
        sys.exit(f'aquarium {name!r}: {"no match" if not matches else "ambiguous"} (have: {names})')
    return matches[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file')
    ap.add_argument('--aquarium', help='aquarium name (default: from the tank column)')
    ap.add_argument('--dry-run', action='store_true', help='validate and report, write nothing')
    args = ap.parse_args()

    with open(args.file, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    if set(READING_COLUMNS) - {'tank'} <= set(header):
        kind, parse, model = 'readings', reading_from_csv_row, Reading
    elif set(EVENT_COLUMNS) - {'tank'} <= set(header):
        kind, parse, model = 'events', event_from_csv_row, Event
    else:
        sys.exit(f'unrecognised header {header}; expected {READING_COLUMNS} or {EVENT_COLUMNS}')

    with app.app_context():
        tanks = {(r.get('tank') or '').strip().lower() for r in rows} - {''}
        if args.aquarium:
            aquarium = find_aquarium(args.aquarium)
        elif len(tanks) == 1:
            aquarium = find_aquarium(tanks.pop())
        else:
            sys.exit(f'tank column has {sorted(tanks) or "no values"}; pass --aquarium')

        parsed, errors = [], []
        for n, row in enumerate(rows, start=2):   # line 1 is the header
            try:
                ts, known, cleaned = parse(row)
                parsed.append((n, ts, known, cleaned))
            except ValueError as e:
                errors.append(f'  line {n}: {e}')
        if errors:
            sys.exit(f'{len(errors)} invalid row(s) in {args.file}, nothing imported:\n' + '\n'.join(errors))

        new, dupes, seen = [], 0, set()
        for n, ts, known, cleaned in parsed:
            match = {k: v for k, v in cleaned.items() if k != 'notes'}
            key = (ts, tuple(sorted(match.items())))
            if key in seen or model.query.filter_by(aquarium_id=aquarium.id, timestamp=ts, **match).first():
                dupes += 1
                continue
            seen.add(key)
            new.append(model(aquarium_id=aquarium.id, timestamp=ts, time_known=known, **cleaned))

        print(f'{args.file}: {len(rows)} {kind} rows for "{aquarium.name.strip()}" '
              f'-> {len(new)} new, {dupes} already present')
        if args.dry_run:
            print('dry run: nothing written')
            return
        db.session.add_all(new)
        db.session.commit()
        print(f'imported {len(new)}')


if __name__ == '__main__':
    main()

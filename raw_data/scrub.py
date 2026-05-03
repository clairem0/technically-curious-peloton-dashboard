"""
Genericize a Peloton export before checking it into a public repo.

What it strips, and why:
- Workout Timestamp: full datetime + timezone -> date only (YYYY-MM-DD).
  The dashboard never uses time-of-day or timezone. Stripping them removes
  signals about sleep schedule, travel patterns, and approximate location.
- Class Timestamp column: dropped entirely.
  This is the original air-date of the recorded class -- not used anywhere
  by the dashboard, and revealed which on-demand library was used.

Workflow:
    1. Re-export from Peloton (Profile -> Workouts -> Download Workouts)
    2. Save the file to raw_data/workouts_raw.csv
    3. Run: python3 raw_data/scrub.py

Reads:  raw_data/workouts_raw.csv      (gitignored -- never committed)
Writes: raw_data/peloton_workouts.csv  (the file checked into git)
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / 'workouts_raw.csv'
DEST = HERE / 'peloton_workouts.csv'

DROP_COLUMNS = {'Class Timestamp'}

with SOURCE.open(newline='') as f_in:
    reader = csv.DictReader(f_in)
    out_fields = [c for c in reader.fieldnames if c not in DROP_COLUMNS]

    with DEST.open('w', newline='') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=out_fields)
        writer.writeheader()
        for row in reader:
            row['Workout Timestamp'] = row['Workout Timestamp'][:10]
            writer.writerow({k: row[k] for k in out_fields})

print(f'Wrote {DEST}')

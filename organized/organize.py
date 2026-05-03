"""
Reads raw_data/peloton_workouts.csv, classifies each row, computes the
dashboard's headline / volume / performance / heatmap / instructor sections,
and writes the result as a single JSON file the HTML loads.

VOLUME = totals + cadence (hours, distance, frequency, streaks)
PERFORMANCE = avg watts scoped to ride_type x duration, FTP tests as discrete
"""
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

RAW_CSV = '../raw_data/peloton_workouts.csv'
OUTPUT_FILE = 'dashboard_data.json'

ROLLING_WINDOW_DAYS = 90  # for the 90-day rolling median signal

# Real-world events that explain shifts in the data
EVENTS = [
    {'date': '2020-03-15', 'label': 'COVID',         'kind': 'context'},
    {'date': '2022-03-01', 'label': 'New bike',      'kind': 'calibration'},
    {'date': '2023-12-03', 'label': 'Recalibration', 'kind': 'calibration'},
]

with open(RAW_CSV, 'r') as f:
    rows = list(csv.DictReader(f))


def classify(title):
    if 'FTP Test' in title: return 'FTP Test'
    if 'Power Zone Max' in title: return 'PZ Max'
    if 'Power Zone Endurance' in title or 'Two for One Power Zone Endurance' in title or 'Global Power Zone Endurance' in title:
        return 'PZ Endurance'
    if 'Power Zone Ride' in title or 'Power Zone EDM' in title or 'Power Zone Pop' in title:
        return 'PZ Standard'
    return None


# ── PERFORMANCE RIDES (cycling, classified, watts > 0) ──
performance = []
zero_watts_classified = 0
for r in rows:
    if r['Fitness Discipline'] != 'Cycling':
        continue
    ride_type = classify(r['Title'])
    if ride_type is None:
        continue
    if not r['Avg. Watts']:
        zero_watts_classified += 1
        continue
    watts = float(r['Avg. Watts'])
    if watts == 0:
        zero_watts_classified += 1
        continue
    date = r['Workout Timestamp'][:10]
    performance.append({
        'date': date,
        'date_obj': datetime.strptime(date, '%Y-%m-%d'),
        'month': date[:7],
        'year': date[:4],
        'ride_type': ride_type,
        'duration': int(r['Length (minutes)']),
        'watts': watts,
        'cadence': float(r['Avg. Cadence (RPM)']) if r['Avg. Cadence (RPM)'] else None,
        'resistance_str': r['Avg. Resistance'],
    })


DURATION_BUCKETS = [
    ('20 min', 20, 20),
    ('45 min', 40, 49),
    ('60 min', 55, 64),
    ('75 min', 70, 79),
    ('90 min', 85, 94),
    ('120 min', 115, 125),
]

def bucket_for(duration):
    for name, lo, hi in DURATION_BUCKETS:
        if lo <= duration <= hi:
            return name
    return None

# ── PERFORMANCE: ride_type × duration → 90-day rolling median ──
# Group rides by (type, duration_bucket)
groups = defaultdict(list)
for r in performance:
    bucket = bucket_for(r['duration'])
    if bucket is None:
        continue
    groups[(r['ride_type'], bucket)].append(r)

# For each group, sort by date and compute scatter + monthly median
performance_series = {}
for (ride_type, bucket), rides in groups.items():
    rides.sort(key=lambda x: x['date_obj'])
    if ride_type not in performance_series:
        performance_series[ride_type] = {}

    # Scatter points (every ride)
    scatter = [
        {'date': r['date'], 'watts': r['watts']}
        for r in rides
    ]

    # Monthly median (with min 2 rides for stability)
    by_month = defaultdict(list)
    for r in rides:
        by_month[r['month']].append(r['watts'])
    monthly = [
        {
            'month': m,
            'median_watts': round(median(vals), 1),
            'rides': len(vals),
        }
        for m, vals in sorted(by_month.items())
        if len(vals) >= 2
    ]

    # 90-day rolling median (right-aligned)
    rolling = []
    for i, r in enumerate(rides):
        window_start = r['date_obj'] - timedelta(days=ROLLING_WINDOW_DAYS)
        window_vals = [x['watts'] for x in rides[:i+1] if x['date_obj'] >= window_start]
        if len(window_vals) >= 3:
            rolling.append({
                'date': r['date'],
                'rolling_median': round(median(window_vals), 1),
                'sample_size': len(window_vals),
            })

    performance_series[ride_type][bucket] = {
        'total_rides': len(rides),
        'scatter': scatter,
        'monthly_median': monthly,
        'rolling_median': rolling,
    }

# ── ANNUAL TABLE per ride_type × duration ──
def percentile(vals, p):
    if not vals: return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c: return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)

annual_summary = {}
for (ride_type, bucket), rides in groups.items():
    if ride_type not in annual_summary:
        annual_summary[ride_type] = {}
    by_year = defaultdict(list)
    for r in rides:
        by_year[r['year']].append(r['watts'])
    annual_summary[ride_type][bucket] = [
        {
            'year': year,
            'rides': len(vals),
            'avg': round(sum(vals) / len(vals), 1),
            'p75': round(percentile(vals, 0.75), 1),
            'p90': round(percentile(vals, 0.90), 1),
            'max': round(max(vals), 1),
        }
        for year, vals in sorted(by_year.items())
    ]

# ── FTP TESTS (discrete) ──
ftp_tests = sorted(
    [{'date': r['date'], 'watts': r['watts']} for r in performance if r['ride_type'] == 'FTP Test'],
    key=lambda x: x['date']
)

# ── ANCILLARY DETECTION ──
# Peloton counts a 15-min warmup + 60-min main ride as 2 separate workouts,
# but they're really one training session. Same with cooldowns.
def is_ancillary(row):
    title = row['Title']
    rtype = row.get('Type', '')
    if 'FTP Warm Up' in title: return True
    if rtype in ('Warm Up', 'Cool Down'): return True
    return False

# ── VOLUME: hours, distance, workouts per month — with discipline split ──
# Group "small" disciplines into "Other" so the chart stays readable
TOP_DISCIPLINES = ['Cycling', 'Strength']

def disc_bucket(d):
    return d if d in TOP_DISCIPLINES else 'Other'

monthly_volume = defaultdict(lambda: {
    'workouts': 0,
    'workouts_ancillary': 0,
    'minutes': 0,
    'minutes_ancillary': 0,
    'miles': 0.0,
    'calories': 0,
    'minutes_by_disc': defaultdict(int),
    'workouts_by_disc': defaultdict(int),
})
for r in rows:
    month = r['Workout Timestamp'][:7]
    bucket = disc_bucket(r['Fitness Discipline'])
    ancillary = is_ancillary(r)
    if ancillary:
        monthly_volume[month]['workouts_ancillary'] += 1
        if r['Length (minutes)']:
            monthly_volume[month]['minutes_ancillary'] += int(r['Length (minutes)'])
    else:
        monthly_volume[month]['workouts'] += 1
        monthly_volume[month]['workouts_by_disc'][bucket] += 1
        if r['Length (minutes)']:
            mins = int(r['Length (minutes)'])
            monthly_volume[month]['minutes'] += mins
            monthly_volume[month]['minutes_by_disc'][bucket] += mins
    if r['Distance (mi)'] and float(r['Distance (mi)']) > 0:
        monthly_volume[month]['miles'] += float(r['Distance (mi)'])
    if r['Calories Burned'] and float(r['Calories Burned']) > 0:
        monthly_volume[month]['calories'] += int(float(r['Calories Burned']))

volume_monthly = []
for m, v in sorted(monthly_volume.items()):
    entry = {
        'month': m,
        'workouts': v['workouts'],                   # excludes warmups/cooldowns
        'workouts_ancillary': v['workouts_ancillary'],
        'hours': round(v['minutes'] / 60, 1),
        'hours_ancillary': round(v['minutes_ancillary'] / 60, 1),
        'miles': round(v['miles'], 1),
        'calories': v['calories'],
        'hours_by_disc': {d: round(v['minutes_by_disc'].get(d, 0) / 60, 1) for d in TOP_DISCIPLINES + ['Other']},
        'workouts_by_disc': {d: v['workouts_by_disc'].get(d, 0) for d in TOP_DISCIPLINES + ['Other']},
    }
    volume_monthly.append(entry)

# ── HEADLINE STATS ──
total_workouts = len(rows)
total_workouts_core = sum(1 for r in rows if not is_ancillary(r))
total_workouts_ancillary = total_workouts - total_workouts_core
total_minutes = sum(int(r['Length (minutes)']) for r in rows if r['Length (minutes)'])
total_minutes_core = sum(int(r['Length (minutes)']) for r in rows if r['Length (minutes)'] and not is_ancillary(r))
total_hours = round(total_minutes / 60, 1)
total_hours_core = round(total_minutes_core / 60, 1)
total_miles = round(sum(float(r['Distance (mi)']) for r in rows if r['Distance (mi)'] and float(r['Distance (mi)']) > 0), 1)
total_calories = int(sum(float(r['Calories Burned']) for r in rows if r['Calories Burned'] and float(r['Calories Burned']) > 0))

# ── STREAKS — the headline insight from Codex ──
# Active weeks (any workout)
active_weeks = set()
for r in rows:
    d = datetime.strptime(r['Workout Timestamp'][:10], '%Y-%m-%d')
    iso_year, iso_week, _ = d.isocalendar()
    active_weeks.add((iso_year, iso_week))

# Find longest consecutive week streak
def consecutive_week_streaks(weeks):
    sorted_weeks = sorted(weeks)
    if not sorted_weeks:
        return 0
    longest = 1
    current = 1
    for i in range(1, len(sorted_weeks)):
        prev = datetime.fromisocalendar(*sorted_weeks[i-1], 1)
        curr = datetime.fromisocalendar(*sorted_weeks[i], 1)
        if (curr - prev).days == 7:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest

longest_week_streak = consecutive_week_streaks(active_weeks)

# Active months (any workout)
active_months = set(r['Workout Timestamp'][:7] for r in rows)

# Total distinct days with at least one workout
active_days = set(r['Workout Timestamp'][:10] for r in rows)

# Performance ride counts
perf_count = len(performance)

# ── HEATMAP — color by daily kJ (training load), not workout count ──
# kJ from cycling captures intensity × duration in one number.
# Strength/stretching days have 0 kJ — we still mark them as a workout day.
daily = defaultdict(lambda: {'count': 0, 'kj': 0})
for r in rows:
    d = r['Workout Timestamp'][:10]
    daily[d]['count'] += 1
    if r['Total Output']:
        try:
            daily[d]['kj'] += int(r['Total Output'])
        except ValueError:
            pass

# Tiers based on Claire's actual distribution (p25/p50/p75/p90 of non-zero days):
#   l0 (no workout): empty cell
#   l1: workout but no cycling kJ (strength-only day)
#   l2: 1–700 kJ      (light cycling)
#   l3: 700–1100 kJ   (moderate)
#   l4: 1100–1500 kJ  (solid)
#   l5: 1500+ kJ      (big day)
def kj_tier(kj):
    if kj == 0: return 1  # workout but no cycling
    if kj < 700: return 2
    if kj < 1100: return 3
    if kj < 1500: return 4
    return 5

heatmap = [
    {
        'date': d,
        'count': v['count'],
        'kj': v['kj'],
        'tier': kj_tier(v['kj']),
    }
    for d, v in sorted(daily.items())
]

# ── INSTRUCTORS ──
instr_counts = defaultdict(int)
for r in rows:
    name = r['Instructor Name'] if r['Instructor Name'] else 'No Instructor'
    instr_counts[name] += 1
instructors = [{'name': n, 'count': c} for n, c in sorted(instr_counts.items(), key=lambda x: -x[1])]

# ── ASSEMBLE ──
dashboard_data = {
    'headline': {
        'total_workouts': total_workouts_core,
        'total_workouts_raw': total_workouts,
        'ancillary_workouts': total_workouts_ancillary,
        'performance_rides': perf_count,
        'total_hours': total_hours_core,
        'total_hours_raw': total_hours,
        'years_active': 8.2,
        'longest_week_streak': longest_week_streak,
        'active_weeks': len(active_weeks),
        'active_months': len(active_months),
        'active_days': len(active_days),
    },
    'volume': {
        'totals': {
            'workouts': total_workouts_core,
            'workouts_raw': total_workouts,
            'ancillary_workouts': total_workouts_ancillary,
            'hours': total_hours_core,
            'hours_raw': total_hours,
            'miles': total_miles,
            'calories': total_calories,
            'around_world_x': round(total_miles / 24901, 2),
        },
        'monthly': volume_monthly,
        'heatmap': heatmap,
    },
    'performance': {
        'series': performance_series,
        'annual': annual_summary,
        'ftp_tests': ftp_tests,
        'ride_types': ['PZ Endurance', 'PZ Standard', 'PZ Max'],
        'duration_buckets': [b[0] for b in DURATION_BUCKETS],
        'data_quality_notes': {
            'rides_with_zero_watts': zero_watts_classified,
            'note': 'Performance-classified cycling rides with 0 watts are excluded — likely sensor failures or skipped rides.',
        },
    },
    'instructors': instructors[:12],
    'events': EVENTS,
}

with open(OUTPUT_FILE, 'w') as f:
    json.dump(dashboard_data, f, indent=2)

# ── REPORT ──
print(f'v6 organized → {OUTPUT_FILE}')
print(f'\nHEADLINE:')
print(f'  Total workouts: {total_workouts:,}')
print(f'  Performance rides: {perf_count:,}')
print(f'  Total hours: {total_hours:,}')
print(f'  Active weeks: {len(active_weeks)}/424 ({len(active_weeks)/424*100:.0f}%)')
print(f'  Longest weekly streak: {longest_week_streak} weeks')
print(f'  Active months: {len(active_months)}/100')
print(f'\nVOLUME totals: {total_workouts:,} workouts, {total_hours:,} hours, {total_miles:,} mi, {total_calories:,} cal')
print(f'\nPERFORMANCE series available:')
for ride_type, buckets in performance_series.items():
    for bucket, data in buckets.items():
        print(f'  {ride_type:<14} {bucket}: {data["total_rides"]} rides, {len(data["monthly_median"])} stable months, {len(data["rolling_median"])} rolling points')
print(f'\nFTP tests: {len(ftp_tests)}')
print(f'Zero-watts performance rides excluded: {zero_watts_classified}')

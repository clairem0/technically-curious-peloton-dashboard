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

# ── VOLUME: time/effort include ancillary rows; counts do not ──
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
    if r['Length (minutes)']:
        mins = int(r['Length (minutes)'])
        monthly_volume[month]['minutes'] += mins
        monthly_volume[month]['minutes_by_disc'][bucket] += mins
        if ancillary:
            monthly_volume[month]['minutes_ancillary'] += mins
    if ancillary:
        monthly_volume[month]['workouts_ancillary'] += 1
    else:
        monthly_volume[month]['workouts'] += 1
        monthly_volume[month]['workouts_by_disc'][bucket] += 1
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
        'hours': round(v['minutes'] / 60, 1),        # includes warmups/cooldowns
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

# ── STREAKS / DAY COUNTS ──
# Warmups/cooldowns count toward time and effort, but not active-day credit.
core_rows = [r for r in rows if not is_ancillary(r)]
core_dates = [datetime.strptime(r['Workout Timestamp'][:10], '%Y-%m-%d') for r in core_rows]

# Active weeks (core workouts only)
active_weeks = set()
for r in core_rows:
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
if core_dates:
    first_week = datetime.fromisocalendar(*min(active_weeks), 1)
    last_week = datetime.fromisocalendar(*max(active_weeks), 1)
    active_week_span = ((last_week - first_week).days // 7) + 1
else:
    active_week_span = 0

# Active months (core workouts only)
active_months = set(r['Workout Timestamp'][:7] for r in core_rows)
if active_months:
    first_month = min(active_months)
    last_month = max(active_months)
    first_year, first_mon = map(int, first_month.split('-'))
    last_year, last_mon = map(int, last_month.split('-'))
    active_month_span = (last_year - first_year) * 12 + (last_mon - first_mon) + 1
else:
    active_month_span = 0

# Total distinct days with at least one core workout
active_days = set(r['Workout Timestamp'][:10] for r in core_rows)

# Performance ride counts
perf_count = len(performance)

# ── HEATMAP — color by estimated daily effort, not workout count ──
# Calories are Peloton estimates, but they cover strength and other disciplines.
# Warmups/cooldowns add effort without inflating the core workout count.
daily = defaultdict(lambda: {'count': 0, 'calories': 0, 'kj': 0})
for r in rows:
    d = r['Workout Timestamp'][:10]
    if not is_ancillary(r):
        daily[d]['count'] += 1
    if r['Calories Burned']:
        try:
            daily[d]['calories'] += int(float(r['Calories Burned']))
        except ValueError:
            pass
    if r['Total Output']:
        try:
            daily[d]['kj'] += int(r['Total Output'])
        except ValueError:
            pass

# Tiers based on the exported daily calorie distribution:
#   l0 (no core workout / no estimated effort): empty cell
#   l1: core workout with no calorie estimate
#   l2: 1–299 cal      (light / strength-only)
#   l3: 300–1,199 cal  (moderate)
#   l4: 1,200–1,599 cal
#   l5: 1,600+ cal
def effort_tier(calories, count):
    if calories == 0 and count > 0: return 1
    if calories < 300: return 2
    if calories < 1200: return 3
    if calories < 1600: return 4
    return 5

heatmap = [
    {
        'date': d,
        'count': v['count'],
        'kj': v['kj'],
        'calories': v['calories'],
        'tier': effort_tier(v['calories'], v['count']),
    }
    for d, v in sorted(daily.items())
    if v['count'] > 0 or v['calories'] > 0
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
        'total_hours': total_hours,
        'total_hours_core': total_hours_core,
        'total_hours_raw': total_hours,
        'years_active': 8.2,
        'longest_week_streak': longest_week_streak,
        'active_weeks': len(active_weeks),
        'active_week_span': active_week_span,
        'active_months': len(active_months),
        'active_month_span': active_month_span,
        'active_days': len(active_days),
    },
    'volume': {
        'totals': {
            'workouts': total_workouts_core,
            'workouts_raw': total_workouts,
            'ancillary_workouts': total_workouts_ancillary,
            'hours': total_hours,
            'hours_core': total_hours_core,
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
print(f'  Core workouts: {total_workouts_core:,} (+{total_workouts_ancillary:,} ancillary)')
print(f'  Performance rides: {perf_count:,}')
print(f'  Training hours: {total_hours:,} ({total_hours_core:,} core)')
print(f'  Active weeks: {len(active_weeks)}/{active_week_span} ({len(active_weeks)/active_week_span*100:.0f}%)')
print(f'  Longest weekly streak: {longest_week_streak} weeks')
print(f'  Active months: {len(active_months)}/{active_month_span}')
print(f'\nVOLUME totals: {total_workouts_core:,} core workouts, {total_hours:,} hours, {total_miles:,} mi, {total_calories:,} cal')
print(f'\nPERFORMANCE series available:')
for ride_type, buckets in performance_series.items():
    for bucket, data in buckets.items():
        print(f'  {ride_type:<14} {bucket}: {data["total_rides"]} rides, {len(data["monthly_median"])} stable months, {len(data["rolling_median"])} rolling points')
print(f'\nFTP tests: {len(ftp_tests)}')
print(f'Zero-watts performance rides excluded: {zero_watts_classified}')

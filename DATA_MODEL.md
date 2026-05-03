# Data Model

Reference documentation for the data flowing through the Peloton dashboard pipeline. Read this when:
- You want to add a new chart and need to know what's available
- You want to understand a number on the dashboard and trace it back
- You want to extend `organize.py` with new aggregations

The source of truth is `organized/organize.py`; this file explains the contract.
Counts and date ranges below describe the current committed export and should be
checked again after a fresh Peloton export.

## ERD: from raw rows to dashboard structures

```
┌────────────────────────────┐
│   RAW WORKOUT (CSV row)    │  ← what Peloton gives you
├────────────────────────────┤
│ Workout Timestamp          │
│ Title                      │  ← drives classification
│ Type                       │  ← drives ancillary detection
│ Length (minutes)           │  ← drives duration bucket
│ Fitness Discipline         │  ← drives volume split
│ Avg. Watts                 │  ← primary fitness metric
│ Total Output (kJ)          │  ← training load metric
│ Distance (mi)              │
│ Calories Burned            │
│ Instructor Name            │
│ ...8 other columns         │
└────────────────────────────┘
              │
              │  organize.py reads each row
              │  applies classify(), is_ancillary(),
              │  bucket_for(), disc_bucket()
              ▼
   ┌──────────┴──────────┐
   │                     │
   ▼                     ▼
┌──────────────┐   ┌──────────────────┐
│ ALL ROWS     │   │ PERFORMANCE RIDE │  ← classified subset
├──────────────┤   ├──────────────────┤
│ used for:    │   │ ride_type        │  (PZ Endurance / PZ Standard /
│ - heatmap    │   │ duration         │   PZ Max / FTP Test)
│ - volume     │   │ duration_bucket  │
│ - instructors│   │ watts            │  (45/60/75/90/120 min)
│ - active days│   │ date_obj         │
└──────────────┘   └──────────────────┘
        │                   │
        │                   │ grouped by (ride_type, duration_bucket)
        │                   │
        │                   ▼
        │         ┌──────────────────────┐
        │         │ PERFORMANCE SERIES   │
        │         ├──────────────────────┤
        │         │ scatter (each ride)  │
        │         │ monthly_median       │
        │         │ rolling_median (90d) │
        │         └──────────────────────┘
        │
        │ grouped by month
        ▼
┌──────────────────────┐
│ VOLUME MONTH         │
├──────────────────────┤
│ workouts (core)      │  excludes ancillary
│ workouts_ancillary   │
│ hours / minutes      │
│ miles                │
│ calories             │
│ hours_by_disc        │  {Cycling, Strength, Other}
│ workouts_by_disc     │
└──────────────────────┘

┌──────────────────────┐
│ HEATMAP DAY          │  one entry per day-with-workout
├──────────────────────┤
│ date                 │
│ count                │  workouts that day (incl ancillary)
│ kj                   │  total cycling kJ
│ tier                 │  1–5 based on kJ thresholds
└──────────────────────┘

┌──────────────────────┐
│ FTP TEST             │  discrete events
├──────────────────────┤
│ date                 │
│ watts                │
└──────────────────────┘

┌──────────────────────┐
│ EVENT                │  hand-authored, in EVENTS list
├──────────────────────┤
│ date                 │
│ label                │
│ kind                 │  'context' or 'calibration'
└──────────────────────┘

┌──────────────────────┐
│ INSTRUCTOR           │
├──────────────────────┤
│ name                 │
│ count                │  total rides led
└──────────────────────┘
```

## JSON schema reference

The full structure of `dashboard_data.json`:

```js
{
  "headline": {
    "total_workouts": 2955,           // core (no warmups)
    "total_workouts_raw": 4474,       // including warmups/cooldowns
    "ancillary_workouts": 1519,
    "performance_rides": 1468,         // tracked PZ + FTP rides only
    "total_hours": 2278.4,             // core
    "total_hours_raw": 2621.1,
    "years_active": 8.2,
    "longest_week_streak": 383,        // consecutive weeks ridden
    "active_weeks": 427,
    "active_months": 100,
    "active_days": 2357
  },

  "volume": {
    "totals": {
      "workouts": 2955,
      "workouts_raw": 4474,
      "ancillary_workouts": 1519,
      "hours": 2278.4,
      "hours_raw": 2621.1,
      "miles": 45563.2,
      "calories": 2505886,
      "around_world_x": 1.83
    },

    "monthly": [
      {
        "month": "2018-02",
        "workouts": 2,                // core
        "workouts_ancillary": 0,
        "hours": 1.8,
        "hours_ancillary": 0.0,
        "miles": 22.1,
        "calories": 1092,
        "hours_by_disc": {            // stacked-chart input
          "Cycling": 1.8,
          "Strength": 0.0,
          "Other": 0.0
        },
        "workouts_by_disc": {
          "Cycling": 2,
          "Strength": 0,
          "Other": 0
        }
      },
      // ...one entry per generated month; current export spans 2018-02 through 2026-05
    ],

    "heatmap": [
      {
        "date": "2018-02-25",
        "count": 1,                   // workouts that day
        "kj": 790,                    // total cycling kJ
        "tier": 3                     // color tier 1–5
      },
      // ...one entry per day with at least one workout
    ]
  },

  "performance": {
    "series": {
      "PZ Endurance": {
        "60 min": {
          "total_rides": 139,
          "scatter": [
            {"date": "2018-03-04", "watts": 215},
            // ...one per ride
          ],
          "monthly_median": [
            {"month": "2020-08", "median_watts": 248.0, "rides": 5},
            // months with ≥2 rides only
          ],
          "rolling_median": [
            {"date": "2020-12-15", "rolling_median": 252.3, "sample_size": 14},
            // ...one per ride with ≥3 rides in trailing 90 days
          ]
        },
        "75 min": { ... },
        "90 min": { ... },
        "120 min": { ... }
      },
      "PZ Standard": {
        "45 min": { ... },
        "60 min": { ... }
      },
      "PZ Max": {
        "20 min": { ... },
        "45 min": { ... }
      },
      "FTP Test": {
        "20 min": { ... }
      }
    },

    "annual": {                       // for the year-over-year table
      "PZ Standard": {
        "60 min": [
          {
            "year": "2021",
            "rides": 69,
            "avg": 269.0,
            "p75": 281.0,
            "p90": 287.0,
            "max": 292.0
          },
          // ...one per year
        ]
      }
    },

    "ftp_tests": [                    // discrete dot plot
      {"date": "2018-05-12", "watts": 254},
      {"date": "2020-12-05", "watts": 363},
      // ...12 total
    ],

    "ride_types": ["PZ Endurance", "PZ Standard", "PZ Max"],
    "duration_buckets": ["20 min", "45 min", "60 min", "75 min", "90 min", "120 min"],

    "data_quality_notes": {
      "rides_with_zero_watts": 158,
      "note": "Performance-classified cycling rides with 0 watts excluded — sensor failures or skipped rides."
    }
  },

  "instructors": [
    {"name": "Matt Wilpers", "count": 3196},
    {"name": "Ben Alldis",   "count":  337},
    // ...top 12
  ],

  "events": [
    {"date": "2020-03-15", "label": "COVID",         "kind": "context"},
    {"date": "2022-03-01", "label": "New bike",      "kind": "calibration"},
    {"date": "2023-12-03", "label": "Recalibration", "kind": "calibration"}
  ]
}
```

## Metric dictionary

| Field | Definition | Notes |
|---|---|---|
| `headline.total_workouts` / `volume.totals.workouts` | Count of rows where `is_ancillary(row)` is false | This is the "core workout" count. |
| `headline.total_workouts_raw` / `volume.totals.workouts_raw` | Count of all Peloton export rows | Includes warmups and cooldowns. |
| `headline.ancillary_workouts` / `volume.totals.ancillary_workouts` | Raw workouts minus core workouts | Warmups/cooldowns are still available for audit. |
| `headline.performance_rides` | Cycling rows with a recognized performance title and nonzero watts | Includes FTP tests; excludes missing or zero `Avg. Watts`. |
| `headline.total_hours` / `volume.totals.hours` | Sum of `Length (minutes)` for non-ancillary rows, divided by 60 | Rounded to 1 decimal. |
| `headline.total_hours_raw` / `volume.totals.hours_raw` | Sum of `Length (minutes)` for all rows, divided by 60 | Rounded to 1 decimal. |
| `headline.years_active` | Hard-coded display value in `organize.py` | Update this when the dataset window changes materially. |
| `headline.longest_week_streak` | Longest run of consecutive ISO weeks with at least one workout | Any workout counts, including ancillary. |
| `headline.active_weeks` | Distinct ISO weeks with at least one workout | Any workout counts. |
| `headline.active_months` | Distinct `YYYY-MM` values in `Workout Timestamp` | Any workout counts. |
| `headline.active_days` | Distinct dates with at least one workout | Same population as the heatmap. |
| `volume.totals.miles` | Sum of positive `Distance (mi)` across all rows | Includes ancillary rows when Peloton reports distance. |
| `volume.totals.calories` | Sum of positive `Calories Burned` across all rows | Calories are estimates; use as directional context. |
| `volume.totals.around_world_x` | `miles / 24901`, rounded to 2 decimals | Uses Earth's circumference in miles as a display comparison. |
| `volume.monthly[].workouts` | Non-ancillary row count for the month | This drives core workout volume. |
| `volume.monthly[].workouts_ancillary` | Ancillary row count for the month | Split out so warmups/cooldowns do not inflate core workout counts. |
| `volume.monthly[].hours` | Non-ancillary minutes for the month divided by 60 | Rounded to 1 decimal. |
| `volume.monthly[].hours_ancillary` | Ancillary minutes for the month divided by 60 | Rounded to 1 decimal. |
| `volume.monthly[].miles` | Positive `Distance (mi)` summed across all rows in the month | Not limited to non-ancillary rows. |
| `volume.monthly[].calories` | Positive `Calories Burned` summed across all rows in the month | Not limited to non-ancillary rows. |
| `volume.monthly[].hours_by_disc` | Non-ancillary minutes by display discipline, divided by 60 | Keys are `Cycling`, `Strength`, `Other`. |
| `volume.monthly[].workouts_by_disc` | Non-ancillary workout count by display discipline | Keys are `Cycling`, `Strength`, `Other`. |

## Performance model contract

The performance model is intentionally narrower than the volume model. Its job
is to compare like with like, not to summarize every ride.

To enter `performance.series`, a row must pass all of these checks:

1. `Fitness Discipline` is `Cycling`.
2. `classify(Title)` returns a performance ride type.
3. `Avg. Watts` is present and greater than zero.
4. `Length (minutes)` falls into one of the configured duration buckets.

Then `organize.py` groups rides by `(ride_type, duration_bucket)` and produces:

| Output | Rule |
|---|---|
| `scatter` | One point per included ride. |
| `monthly_median` | Median watts per month, only when that month has at least 2 included rides for the same type + bucket. |
| `rolling_median` | Right-aligned 90-day median watts, only when the trailing window has at least 3 included rides for the same type + bucket. |
| `annual` | Yearly `avg`, `p75`, `p90`, and `max` watts for each observed type + bucket. No minimum ride count is applied. |
| `ftp_tests` | Included FTP test rows pulled out again as a discrete dot-plot series. |

The model deliberately does not compare watts across unlike ride types or
durations. A 45-minute Power Zone Max ride and a 120-minute Power Zone Endurance
ride are different cohorts.

`cadence` and `resistance_str` are parsed inside the intermediate `performance`
records, but they are not currently written to `dashboard_data.json`.

## Generated domains

Some arrays look like enums, but most of the schema is generated from observed
data:

- `performance.series` and `performance.annual` are sparse. Do not assume every
  ride type has every duration bucket.
- `performance.ride_types` is a display selector for trend charts and excludes
  `FTP Test`, even though `FTP Test` exists under `performance.series`.
- `performance.duration_buckets` comes from `DURATION_BUCKETS` in `organize.py`;
  it lists supported buckets, not guaranteed type + bucket combinations.
- `events.kind` is a display convention. Current values are `context` and
  `calibration`; the code does not enforce this as a closed enum.
- Discipline display buckets are fixed by `TOP_DISCIPLINES = ['Cycling',
  'Strength']`; every other Peloton discipline maps to `Other`.

## Classification rules

These are the business rules that turn raw rows into structured data. They live in `organize.py`.

### `classify(title)` — what kind of performance ride is this?

| Condition | Returns |
|---|---|
| Title contains `'FTP Test'` | `'FTP Test'` |
| Title contains `'Power Zone Max'` | `'PZ Max'` |
| Title contains `'Power Zone Endurance'` (incl. "Two for One" / "Global") | `'PZ Endurance'` |
| Title contains `'Power Zone Ride'`, `'Power Zone EDM'`, or `'Power Zone Pop'` | `'PZ Standard'` |
| Otherwise | `None` (not a tracked performance ride) |

### `is_ancillary(row)` — is this a warmup or cooldown?

| Condition | Returns |
|---|---|
| Title contains `'FTP Warm Up'` | `True` |
| `Type` is `'Warm Up'` or `'Cool Down'` | `True` |
| Otherwise | `False` |

Ancillary rides are excluded from "real workout" counts and "real hours" totals.

### `bucket_for(duration)` — which duration bucket does this ride fall into?

| Duration (minutes) | Bucket |
|---|---|
| 20 | `'20 min'` |
| 40–49 | `'45 min'` |
| 55–64 | `'60 min'` |
| 70–79 | `'75 min'` |
| 85–94 | `'90 min'` |
| 115–125 | `'120 min'` |
| Other | `None` (not bucketed) |

### `disc_bucket(discipline)` — how should this discipline appear in the volume chart?

| Discipline | Bucket |
|---|---|
| `'Cycling'` | `'Cycling'` |
| `'Strength'` | `'Strength'` |
| Anything else (Running, Stretching, etc.) | `'Other'` |

### Heatmap kJ tiers

| Daily kJ | Tier | Color |
|---|---|---|
| Day with workout, 0 cycling kJ (strength only) | 1 | lightest tan |
| 1–699 | 2 | light orange |
| 700–1,099 | 3 | mid orange |
| 1,100–1,499 | 4 | deep orange |
| 1,500+ | 5 | deep rust |

Thresholds are based on Claire's actual distribution (p25/p50/p90 of non-zero days). For a different rider, you'd recalibrate.

## Extending the data model

To add a new aggregation (e.g. instructor performance breakdown):

1. **In `organize.py`**, make the source field available to the aggregation. For
   instructor performance, that means carrying instructor into each performance
   record:
   ```python
   performance.append({
       ...,
       'instructor': r['Instructor Name'] or 'No Instructor',
   })
   ```

2. **Add the aggregation in `organize.py`**:
   ```python
   instructor_perf = defaultdict(list)
   for r in performance:
       instructor_perf[r['instructor']].append(r['watts'])
   instructor_avg = {name: sum(w)/len(w) for name, w in instructor_perf.items()}
   ```

3. **Add it to `dashboard_data`** at the bottom:
   ```python
   dashboard_data = {
       ...,
       'instructor_performance': instructor_avg,
   }
   ```

4. **Document the new shape in this file** so future edits know what the field
   means and which rows it includes.

5. **In `dashboard.html`**, add an empty container and a JS block that reads `DATA.instructor_performance`.

6. Re-run organize, re-inject, refresh.

## Regeneration checklist

After a fresh Peloton export:

1. Run `python3 raw_data/scrub.py`.
2. Run `cd organized && python3 organize.py`.
3. Validate `organized/dashboard_data.json` parses as JSON.
4. Check first/last months in `volume.monthly`.
5. Check headline counts and `data_quality_notes.rides_with_zero_watts`.
6. Update any snapshot values in this document that changed materially.

## Data quality caveats

| Source of noise | What we do |
|---|---|
| 158 cycling rides with 0 watts (sensor failure) | Excluded from performance series |
| Ancillary warmups/cooldowns inflate workout counts | Excluded from `workouts` (visible in `workouts_raw`) |
| Bike calibration changed in Mar 2022 and Dec 2023 | Marked with vertical lines; not used as causal explanation |
| `Avg. Heartrate` column has only 1 nonzero value across 4,474 rows | Ignored entirely — not usable |
| Mixing across durations smooths watts misleadingly | All performance metrics scoped to type × duration |
| Calories are estimates with wide error bars | Shown but labeled "Estimated · noisy" |

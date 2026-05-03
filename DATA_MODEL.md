# Data Model

Reference documentation for the data flowing through the Peloton dashboard pipeline. Read this when:
- You want to add a new chart and need to know what's available
- You want to understand a number on the dashboard and trace it back
- You want to extend `organize.py` with new aggregations

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
        "workouts": 7,                // core
        "workouts_ancillary": 2,
        "hours": 8.5,
        "hours_ancillary": 0.5,
        "miles": 78.3,
        "calories": 5230,
        "hours_by_disc": {            // stacked-chart input
          "Cycling": 7.2,
          "Strength": 1.3,
          "Other": 0.0
        },
        "workouts_by_disc": {
          "Cycling": 6,
          "Strength": 1,
          "Other": 0
        }
      },
      // ...one entry per month from 2018-02 through 2026-04
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

1. **In `organize.py`**, add a new section that computes what you want:
   ```python
   instructor_perf = defaultdict(list)
   for r in performance:
       instructor_perf[r['instructor']].append(r['watts'])
   instructor_avg = {name: sum(w)/len(w) for name, w in instructor_perf.items()}
   ```

2. **Add it to `dashboard_data`** at the bottom:
   ```python
   dashboard_data = {
       ...,
       'instructor_performance': instructor_avg,
   }
   ```

3. **In `dashboard.html`**, add an empty container and a JS block that reads `DATA.instructor_performance`.

4. Re-run organize, re-inject, refresh.

## Data quality caveats

| Source of noise | What we do |
|---|---|
| 158 cycling rides with 0 watts (sensor failure) | Excluded from performance series |
| Ancillary warmups/cooldowns inflate workout counts | Excluded from `workouts` (visible in `workouts_raw`) |
| Bike calibration changed in Mar 2022 and Dec 2023 | Marked with vertical lines; not used as causal explanation |
| `Avg. Heartrate` column has only 1 nonzero value across 4,474 rows | Ignored entirely — not usable |
| Mixing across durations smooths watts misleadingly | All performance metrics scoped to type × duration |
| Calories are estimates with wide error bars | Shown but labeled "Estimated · noisy" |

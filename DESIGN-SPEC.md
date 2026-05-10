# Design Spec

This design spec documents the intended product, data boundaries, metric
choices, and interface structure for the Peloton dashboard.

## Purpose

Build a static, auditable training dashboard from a Peloton workout export.

The dashboard should answer three different questions without collapsing them
into one misleading score:

1. How much training happened?
2. How consistent was the practice?
3. Is comparable cycling power improving, declining, or changing by era?

This repo is also a companion example for the Technically Curious article
"Build a Dashboard with AI", so the implementation should stay teachable:
raw data in one place, calculations in one place, and visualization as a thin
display layer.

## Audience

Primary audience:

- The rider, as a serious athlete reviewing long-term training honestly.

Secondary audience:

- Agent builders interested in learning how to create dashboards with AI.
- Future maintainers who need to refresh the export, trace a number, or add a
  chart without reverse-engineering the whole repo.

## Product Shape

This is a static personal dashboard, not a web app.

Required properties:

- Opens as a self-contained HTML dashboard.
- Requires no backend, login, database, Peloton API integration, or app server.
- Keeps generated dashboard data small enough to inspect directly.
- Makes every displayed number traceable through `organized/dashboard_data.json`
  and `organized/organize.py`.
- Can be hosted through GitHub Pages or opened locally from
  `dashboard/dashboard.html`.

Non-goals:

- No live sync from Peloton.
- No user accounts or permissions.
- No write-back to Peloton.
- No coaching recommendations.
- No attempt to infer fitness from heart rate or resistance unless those fields
  are proven usable for the current export.
- No single all-purpose "fitness score."

## Core Design Principles

### 1. Separate Volume From Performance

Training volume and fitness are related, but they are not the same thing.

Volume views may show hours, workout counts, distance, calories, and discipline
mix. Performance views should use comparable cycling power only.

The dashboard must not imply that a high-mileage month, high-calorie month, or
high-workout-count month automatically means stronger riding.

### 2. Compare Like With Like

Average watts are meaningful only inside comparable cohorts.

The performance model must scope cycling power by:

- ride type
- duration bucket
- date or era

Examples of valid comparisons:

- 60-minute PZ Standard rides over time
- 90-minute PZ Endurance rides over time
- FTP test results as discrete benchmark points

Examples of invalid default comparisons:

- 45-minute PZ Max versus 120-minute PZ Endurance
- all Power Zone rides blended into one global watts trend
- pre/post bike-change averages without calling out the measurement break

### 3. Treat Calibration Events As Measurement Breaks

The bike change on `2022-03-01` and recalibration on `2023-12-03` are
measurement-context events. They should appear on watts charts, but they should
not be treated as automatic causal explanations.

The chart design should make the break visible and encourage era-aware
interpretation. A simple pre/post split is useful context, not the whole story.

### 4. Keep Calculations Out Of The Browser

`organized/organize.py` owns business logic:

- row classification
- ancillary workout handling
- duration bucketing
- monthly aggregation
- rolling medians
- streaks and active-period counts
- event definitions
- data-quality exclusions

`dashboard/dashboard.html` owns display logic:

- layout
- controls
- chart rendering
- tooltips
- responsive behavior
- PNG export

If a displayed number is wrong, fix or inspect the organizer first.

### 5. Preserve Privacy By Minimizing The Export

The committed CSV should be scrubbed before it enters the repo.

The scrubber should:

- reduce `Workout Timestamp` to date only
- remove `Class Timestamp`
- keep only fields needed for analysis and audit

Anything embedded in `dashboard/dashboard.html` should be considered public if
the repo or GitHub Pages site is public.

`.gitignore` is a guardrail, not a guarantee. Fresh raw exports must never be
force-staged with `git add -f`; only the scrubbed CSV belongs in git.

## Data Pipeline

The expected pipeline is:

```text
raw_data/workouts_raw.csv
  -> raw_data/scrub.py
  -> raw_data/peloton_workouts.csv
  -> organized/organize.py
  -> organized/dashboard_data.json
  -> dashboard/dashboard.html
```

Responsibilities:

| Layer | File | Responsibility |
|---|---|---|
| Gather | `raw_data/workouts_raw.csv` | Fresh Peloton export, gitignored. |
| Scrub | `raw_data/scrub.py` | Remove export fields that are not needed or are too revealing. |
| Source | `raw_data/peloton_workouts.csv` | Scrubbed, committed source data. |
| Organize | `organized/organize.py` | Compute all dashboard-ready structures. |
| Contract | `organized/dashboard_data.json` | Generated JSON consumed by the dashboard. |
| Visualize | `dashboard/dashboard.html` | Render the dashboard and export images. |
| Publish | `index.html` | Redirect GitHub Pages to the dashboard. |

## Data Model Requirements

The generated JSON must include these top-level domains:

- `headline`
- `volume`
- `performance`
- `instructors`
- `events`

The detailed schema belongs in `DATA_MODEL.md`. This design spec only defines
what each domain is for.

### `headline`

Purpose: provide a quick read on the scale and consistency of the training
practice.

Required headline concepts:

- core workout count
- tracked performance ride count
- total training hours
- longest active-week streak

These should be practice signals, not vanity claims.

### `volume`

Purpose: show the body of work.

Volume must support:

- monthly hours
- monthly core workout counts
- ancillary workout counts
- discipline split
- total miles
- estimated calories
- daily consistency heatmap

Rules:

- Warmups and cooldowns count toward time and estimated effort.
- Warmups and cooldowns do not count as core workouts or active-day credit.
- Calories may be used for all-discipline effort coloring because they cover
  non-bike work, but they must be treated as estimates.
- Distance may be shown as cumulative context, but not as primary fitness
  evidence.

### `performance`

Purpose: show comparable cycling power trends.

Rows enter the performance model only when they are:

- cycling workouts
- classified as a tracked Power Zone or FTP ride
- positive-watt rides
- bucketed into a supported duration

Required outputs:

- individual ride scatter points
- monthly medians when there are at least two rides in the same month/cohort
- 90-day rolling medians when there are at least three rides in the window
- FTP tests as discrete benchmark points
- data-quality notes for excluded zero-watt rides

The default performance chart should show one cohort at a time: ride type plus
duration bucket.

### `instructors`

Purpose: summarize workout mix, not performance.

Instructor counts are useful as context about training style and source mix.
They should not be used to rank coaching quality or athlete output.

### `events`

Purpose: annotate interpretation context.

Supported kinds:

- `context`: general life or training context; may appear on volume charts
- `calibration`: measurement or equipment context; should appear on watts charts

Current events:

- `2020-03-15`: COVID
- `2022-03-01`: New bike
- `2023-12-03`: Recalibration

## Interface Requirements

The dashboard should be one editorial, scrollable page with four sections:

1. Masthead and headline stats
2. Training volume
3. Power trends
4. Instructor mix

### Masthead

The masthead should make the subject and time span obvious:

- Peloton training dashboard
- workout history from February 2018 through the latest export month
- organized around volume, consistency, and comparable power metrics

### Headline Stats

The headline row should be fast to scan and should avoid fragile metrics.

Preferred stats:

- core workouts
- performance rides
- total hours
- longest active-week streak

Avoid making calories, distance, or "around the world" the primary headline
unless the surrounding copy clearly frames them as cumulative context.

### Training Volume

The volume section should include:

- stat cards for total scale
- a monthly chart with controls for hours, workouts, miles, and calories
- a daily heatmap for consistency

The default monthly view should be training hours split by discipline, because
hours are more stable than workout counts and less bike-calibration-dependent
than miles.

### Power Trends

The power section should include:

- ride-type selector
- duration selector based on available cohorts
- individual ride points
- 90-day rolling median
- calibration event lines

The section copy and chart labels must make clear that watts are average watts
inside the selected cohort. The chart should not present blended watts as the
overall answer.

FTP tests should be available as benchmark points, not smoothed into a generic
trend line.

### Instructor Mix

The instructor section should show top instructors by workout count across the
export. It is a composition view, not a performance view.

### Export

The page and major chart cards should support PNG export for sharing in docs,
decks, or articles.

Exports should render at a stable width so chart labels and layout are
consistent.

## Visual Design Direction

The dashboard should feel like an editorial analytics artifact:

- calm, off-white page background
- white chart cards with subtle borders
- serif display typography for titles and major numbers
- sans-serif typography for controls and labels
- mono uppercase labels for small metadata
- rust accent for Peloton/power emphasis
- deep teal for volume and practice signals
- restrained gold for contextual footnotes

The visual style should support trust and readability. It should not look like a
gamified fitness app, marketing landing page, or dense BI console.

Charts should prioritize:

- legible trend reading
- visible measurement breaks
- cohort specificity
- restrained color
- tooltips that explain the exact metric shown

## Data Quality Rules

The dashboard must be explicit about known caveats:

- Zero-watt classified rides are excluded from performance series.
- Heart-rate data is not reliable enough to drive the dashboard unless a future
  export proves otherwise.
- Resistance is not a default performance signal.
- Calories are estimates and should stay secondary.
- Distance is bike-calibration-sensitive and should stay secondary.
- Cross-duration watts comparisons are misleading.
- The bike change and recalibration are interpretive markers, not proof of
  causation.

## Acceptance Criteria

A refresh is successful when:

1. `raw_data/scrub.py` produces a scrubbed committed CSV from a fresh export.
2. `organized/organize.py` regenerates valid `organized/dashboard_data.json`.
3. `dashboard/dashboard.html` uses the regenerated data.
4. The dashboard opens locally without a dev server.
5. Headline counts match the generated JSON.
6. Volume charts and heatmap render from `volume`.
7. Power charts render from `performance.series`.
8. Event markers appear only where their kind is appropriate.
9. PNG export works for the full dashboard and chart cards.
10. Any new metric is documented in `DATA_MODEL.md`.

## Future Extension Rules

Add a new chart only when it answers a distinct question.

Good future additions:

- era-aware fixed-duration comparison table
- explicit pre-bike, transition, and post-recalibration summaries
- FTP benchmark panel with sparse-data caveat
- consistency distribution by year

Avoid:

- more cumulative vanity stats
- charts driven by weak source columns
- blended power metrics that hide ride mix
- hidden business logic in dashboard JavaScript

The guiding rule: the dashboard should make the honest interpretation easier,
even when the honest interpretation is less flattering or less simple.

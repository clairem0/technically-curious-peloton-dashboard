# Peloton Dashboard

A concrete companion example for the forthcoming Technically Curious article
[Build a Dashboard with AI](https://technicallycurious.substack.com/p/cda35881-34c9-4aa3-94c2-6edf82de4f68).

This repo turns eight years of Peloton workout history into a self-contained HTML
dashboard. It follows the article's core pattern:

1. **Gather** raw data in one place.
2. **Organize** it into a clean, auditable data model.
3. **Visualize** it with a thin display layer.

The important design choice: the dashboard is not a full app. There is no server,
login, or live database. It is a static HTML file with the data baked in, which is
the right level of complexity for a personal, single-source dashboard.

## What this dashboard answers

Two questions, kept intentionally separate:

1. **Training volume** — hours and estimated effort across all workouts, with warmups and cooldowns included in time but excluded from workout counts.
2. **Power trends** — output scoped to comparable ride types and durations.

The analysis keeps volume, consistency, and power separate so high-mileage or
high-hour months do not get mistaken for stronger riding months.

## How this maps to the article

| Article step | This repo | Why it exists |
|---|---|---|
| **Gather** | `raw_data/peloton_workouts.csv` | A scrubbed Peloton CSV export with 4,490 rows. |
| **Organize** | `organized/organize.py` | Classifies rides, computes monthly volume, builds rolling medians, and writes clean JSON. |
| **Data model** | `DATA_MODEL.md` | Documents the entities, schema, and calculation boundaries so numbers can be traced. |
| **Visualize** | `dashboard/dashboard.html` | Reads the generated JSON and renders the finished dashboard with Chart.js. |
| **Share** | `index.html`, `docs/` + GitHub Pages | Makes the static dashboard and companion docs viewable at URLs without adding an app backend. |

All calculations belong in `organized/organize.py`. The HTML should mostly
position charts, render tooltips, and handle display behavior. If a number is
wrong, debug the JSON before changing the visualization.

## Project structure

```
peloton-dashboard/
├── README.md
├── DESIGN-SPEC.md              ← product/design spec and metric guardrails
├── DATA_MODEL.md                ← ERD + JSON schema reference
├── index.html                   ← redirects GitHub Pages to the dashboard
├── docs/                        ← companion explainer pages and article visuals
│   ├── index.html               ← docs landing page
│   ├── data-model-explainer.html
│   └── visuals/
│       ├── data-flow.html
│       └── organized-data-schema.html
├── raw_data/
│   ├── peloton_workouts.csv     ← scrubbed Peloton export, tracked in git
│   └── scrub.py                 ← genericizes a fresh export before commit
├── organized/
│   ├── organize.py              ← reads CSV, computes everything, writes JSON
│   └── dashboard_data.json      ← clean, structured dashboard data
└── dashboard/
    └── dashboard.html           ← self-contained dashboard with data baked in
```

## Open the dashboard

```bash
open dashboard/dashboard.html
```

The dashboard is self-contained after build: the JSON data is pasted directly
into the HTML as `const DATA = ...`. It still loads Chart.js and Google Fonts
from CDNs, so the first visual render needs internet access unless your browser
has already cached those assets.

## Refresh the data

Use this when you export fresh Peloton data and want to rebuild the dashboard.
This is the repo's manual version of the article's pull → transform → visualize
refresh pipeline.

```bash
# 1. Gather: export from Peloton
# Peloton website → Profile → Workouts → Download Workouts
# Save the fresh export as raw_data/workouts_raw.csv.
# This filename is gitignored.

# 2. Scrub: remove personal/export-only fields before committing
python3 raw_data/scrub.py

# 3. Organize: regenerate the structured JSON
cd organized && python3 organize.py

# 4. Visualize: bake the fresh JSON into the HTML dashboard
cd .. && python3 -c "
import json
with open('organized/dashboard_data.json') as f: data = json.load(f)
with open('dashboard/dashboard.html') as f: html = f.read()
start = html.find('const DATA = {')
i = start + len('const DATA = '); depth = 0; end = None
while i < len(html):
    if html[i] == '{': depth += 1
    elif html[i] == '}':
        depth -= 1
        if depth == 0 and html[i+1] == ';': end = i+2; break
    i += 1
new = html[:start] + 'const DATA = ' + json.dumps(data) + ';' + html[end:]
with open('dashboard/dashboard.html', 'w') as f: f.write(new)
"

# 5. Review the result
open dashboard/dashboard.html
```

### Refresh safety checklist

Before committing a refreshed dashboard, verify the raw export stayed out of
git and only scrubbed/generated files are staged.

```bash
# Raw Peloton export should be ignored, not tracked.
git status --short --ignored=matching raw_data/workouts_raw.csv
git ls-files raw_data/workouts_raw.csv

# Scrubbed CSV should not contain export-only columns.
head -n 1 raw_data/peloton_workouts.csv

# Workout timestamps in the committed CSV should be date-only.
awk -F, 'NR>1 && $1 ~ /[0-9]{2}:[0-9]{2}/ {print NR ":" $1; found=1; exit} END {if (!found) print "ok: date-only workout timestamps"}' raw_data/peloton_workouts.csv

# Generated JSON should parse.
python3 -c 'import json; json.load(open("organized/dashboard_data.json")); print("ok: dashboard_data.json parses")'
```

Expected results:

- `git status --ignored` may show `!! raw_data/workouts_raw.csv`.
- `git ls-files raw_data/workouts_raw.csv` should print nothing.
- `head -n 1 raw_data/peloton_workouts.csv` should not include
  `Class Timestamp`.
- Never run `git add -f raw_data/workouts_raw.csv`.
- Stage only the scrubbed CSV, generated JSON, and baked HTML for a data
  refresh: `raw_data/peloton_workouts.csv`,
  `organized/dashboard_data.json`, and `dashboard/dashboard.html`.

## Pipeline architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   GATHER        │     │   ORGANIZE          │     │   VISUALIZE     │
│                 │ ──> │                     │ ──> │                 │
│ Peloton CSV     │     │ organize.py         │     │ dashboard.html  │
│ raw export      │     │ ↓                   │     │ reads JSON,     │
│ scrubbed copy   │     │ dashboard_data.json │     │ draws charts    │
└─────────────────┘     └─────────────────────┘     └─────────────────┘
   one source           auditable logic             thin display layer
```

The separation is the point. Each layer has one job:

- **Gather** keeps the raw material recognizable and repeatable.
- **Organize** owns classification, aggregation, rolling windows, data-quality exclusions, and event markers.
- **Visualize** turns structured data into charts without hiding business logic in the browser.

This makes the dashboard easier to audit. Wrong total? Check
`organized/dashboard_data.json` and `organized/organize.py`. Wrong chart color,
label, or interaction? Check `dashboard/dashboard.html`.

## Data model

Read [DATA_MODEL.md](./DATA_MODEL.md) when you want to trace a number or add a
new chart. It documents:

- the raw Peloton fields that matter
- ride classification rules
- ancillary workout handling
- monthly volume structures
- performance ride series
- FTP test and event-marker structures
- JSON schema consumed by the dashboard

That file is the saved spec/data map from the article's workflow. It is the
thing you come back to when the dashboard changes.

## Verification checklist

Use the same review posture from the article: you are checking a collaborator's
work, not trusting a black box.

- **Start with known facts.** Confirm the raw export row count, core workout
  count, total hours, and current streak against Peloton.
- **Trace one number end to end.** Pick a headline metric, find it in
  `dashboard_data.json`, then find the calculation in `organize.py`.
- **Look for missing categories.** Make sure non-cycling workouts, warmups,
  cooldowns, and zero-watt rides are handled intentionally.
- **Challenge assumptions.** Ride type and duration comparisons only make sense
  when the cohorts are comparable; do not mix output across unlike rides.
- **Keep context explicit.** Context events can appear on volume charts;
  calibration events should render only on watts charts.

## Common edits

### Add an event marker

Events are a list of dicts in `organized/organize.py`. Find `EVENTS = [...]`
and add a row:

```python
EVENTS = [
    {'date': '2020-03-15', 'label': 'COVID',         'kind': 'context'},
    {'date': '2022-03-01', 'label': 'New bike',      'kind': 'calibration'},
    {'date': '2023-12-03', 'label': 'Recalibration', 'kind': 'calibration'},
    {'date': '2025-06-01', 'label': 'Knee injury',   'kind': 'context'},
]
```

Re-run the refresh pipeline. The dashboard's `eventLines` plugin reads from
`DATA.events`; context markers can appear on volume charts, while calibration
markers should stay limited to watts charts.

### Add a chart

Start in the organize layer:

1. Add the aggregation to `organized/organize.py`.
2. Write the result into `dashboard_data.json`.
3. Document the new shape in `DATA_MODEL.md`.
4. Render it from `dashboard/dashboard.html`.

If the chart requires a new calculation, do that calculation in Python first.
The browser should receive chart-ready data.

## Sharing and deployment

This repo is in the static-dashboard tier from the article:

- **Email / local file:** send or open `dashboard/dashboard.html`.
- **PNG export:** use the dashboard button when someone needs a snapshot for a deck.
- **GitHub Pages:** use `index.html` to serve the dashboard from a clean URL.
  The companion docs live under `docs/`.

For GitHub Pages, configure the repository to publish from `main` / root. With
that setting, the dashboard resolves from the repository homepage and the docs
resolve from `/docs/`:

```text
https://<github-user>.github.io/technically-curious-peloton-dashboard/
https://<github-user>.github.io/technically-curious-peloton-dashboard/docs/
```

Static hosting is enough because the data is personal, single-user, and updated
manually. If you publish this repo or host it publicly, assume anything baked
into `dashboard/dashboard.html` or `docs/` is public.

## When to graduate from JSON

JSON is the right call here: the generated dashboard data is small, readable,
and easy to bake into one HTML file. Consider PostgreSQL or another database
only when one of these becomes true:

- **The file gets painful.** A few MB of embedded JSON is usually fine. Larger
  files become slow to inspect and awkward to ship.
- **You need ad-hoc queries.** If you want to ask new questions without editing
  `organize.py`, a database gives you a better query layer.
- **You combine multiple sources.** Apple Health, Strava, sleep, injuries, and
  Peloton data would be cleaner as related tables than one expanding JSON blob.
- **You need automated refreshes.** Nightly or live updates are more robust when
  scripts read and write a database instead of replacing a static file.
- **Multiple people need different access.** Once users need permissions,
  write-back, or live data, you are building an app.

For a single-user, single-source Peloton dashboard with monthly refreshes, the
static HTML + JSON approach is intentionally enough.

## See also

- [DESIGN-SPEC.md](./DESIGN-SPEC.md) — product/design spec and metric guardrails
- [DATA_MODEL.md](./DATA_MODEL.md) — schema reference and calculation map
- [docs/](./docs/) — companion explainer pages and article visuals
- [Technically Curious](https://technicallycurious.substack.com/) — practical AI workflows for people past basic prompting

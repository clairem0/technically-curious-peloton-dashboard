# Peloton Dashboard

A personal training dashboard built from 8 years of Peloton workout history. Follows the [Build a Dashboard with AI](#) Gather → Organize → Visualize pattern.

## What this dashboard answers

Two questions, kept honest by separating them:

1. **How much** — total volume (hours, miles, workouts, training load over time)
2. **How strong** — power output trends scoped to ride type + duration

Plus the headline framing: an unbroken weekly streak going back to 2018.

## Project structure

```
peloton-dashboard/
├── README.md                    ← you are here
├── DATA_MODEL.md                ← ERD + JSON schema reference
├── raw_data/
│   ├── peloton_workouts.csv    ← scrubbed Peloton export, 4,474 rows
│   └── scrub.py                ← genericizes a fresh export before commit
├── organized/
│   ├── organize.py             ← reads CSV, computes everything, writes JSON
│   └── dashboard_data.json     ← clean, structured data file
└── dashboard/
    └── dashboard.html          ← self-contained dashboard (data baked in)
```

## How to refresh

When you want to pull fresh Peloton data and update the dashboard:

```bash
# 1. Re-export from Peloton website (Profile → Workouts → Download Workouts)
# 2. Save it as raw_data/workouts_raw.csv (this filename is gitignored)
# 3. Scrub it (strips time-of-day + timezone, drops Class Timestamp column):
python3 raw_data/scrub.py
# This produces raw_data/peloton_workouts.csv -- the file the repo tracks.

# 4. Re-run organize:
cd organized && python3 organize.py

# 5. Re-inject the data into the HTML:
cd .. && python3 -c "
import json
with open('organized/dashboard_data.json') as f: data = json.load(f)
with open('dashboard/dashboard.html') as f: html = f.read()
# Find existing DATA declaration and replace
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

# 6. Open it
open dashboard/dashboard.html
```

## The architecture (Gather → Organize → Visualize)

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   GATHER        │     │   ORGANIZE          │     │   VISUALIZE     │
│                 │ ──> │                     │ ──> │                 │
│ Peloton CSV     │     │ organize.py         │     │ dashboard.html  │
│ (raw, messy)    │     │ ↓                   │     │ Reads JSON,     │
│ 4,474 rows ×    │     │ dashboard_data.json │     │ draws charts    │
│ 17 columns      │     │                     │     │                 │
└─────────────────┘     └─────────────────────┘     └─────────────────┘
   you download         all logic lives here        pure display layer
```

**The principle:** all calculations, classifications, and aggregations happen in `organize.py`. The HTML file does no math — it reads from the JSON and paints charts. This makes the system easy to debug (wrong number → check JSON; wrong color → check HTML) and easy to refresh (re-run organize, re-inject).

## FAQ

### When I email the HTML, do the values go with it?

**Yes.** When you build the dashboard, all the data gets baked directly into the HTML file. Specifically: the HTML template has a placeholder line —

```javascript
const DATA = DASHBOARD_DATA_PLACEHOLDER;
```

— and the build step (the Python snippet under "How to refresh") reads `dashboard_data.json` and pastes its entire contents into that line, producing:

```javascript
const DATA = {"headline":{"total_workouts":2955,...};   // ← all 372KB inline
```

Once that's done, the file is fully self-contained. No server, no external data fetch, no JSON file required at runtime. You can email it, drop it on GitHub Pages, open it offline. Caveat: it loads Chart.js and Google Fonts from CDNs, so the visuals need internet on first load (browsers cache them after).

### Where does the actual computation happen?

Everything happens in `organize.py` — this is the "Organize" step from the dashboard article in action. The script does three kinds of work:

1. **Classify** — for each row in the CSV, decide what kind of workout it is. Helper functions like `classify(title)` return whether a ride is `PZ Endurance` / `PZ Standard` / `PZ Max` / `FTP Test` based on the title; `is_ancillary(row)` flags warmups and cooldowns; `bucket_for(duration)` maps minute-counts into duration buckets (45/60/75/90/120 min).

2. **Aggregate** — walk through 4,474 rows and group them. Monthly volume gets summed using `defaultdict`s. Performance series get bucketed by `(ride_type, duration)`, sorted by date, then run through a 90-day rolling window to compute trend lines.

3. **Assemble** — bundle everything into one Python dict matching the JSON schema (see DATA_MODEL.md), then write it out:
   ```python
   with open(OUTPUT_FILE, 'w') as f:
       json.dump(dashboard_data, f, indent=2)
   ```

The HTML's JavaScript only does layout work: positioning chart points, generating heatmap cells, attaching tooltips. If a chart shows a wrong number, the wrong number is already in the JSON — so debugging starts in `organize.py`, not in the HTML.

### Can I add my own event marker?

Yes — events are just a list of dicts in `organize.py`. Three steps:

1. **Open `organize.py`** and find the `EVENTS = [...]` list near the top of the file.
2. **Add your entry.** It needs three fields: `date` (YYYY-MM-DD), `label` (short text shown on the chart), and `kind` (either `'context'` for grey lines like COVID, or `'calibration'` for gold lines like a bike change). Example:
   ```python
   EVENTS = [
       {'date': '2020-03-15', 'label': 'COVID',         'kind': 'context'},
       {'date': '2022-03-01', 'label': 'New bike',      'kind': 'calibration'},
       {'date': '2023-12-03', 'label': 'Recalibration', 'kind': 'calibration'},
       {'date': '2025-06-01', 'label': 'Knee injury',   'kind': 'context'},  # new
   ]
   ```
3. **Re-run the build** (organize → inject → reload). The line shows up on every time-series chart automatically — the dashboard's `eventLines` plugin reads from `DATA.events` and draws all of them.

No chart code changes. Adding an event in one place updates all five charts.

### What chart library is this?

A **chart library** is a pre-built piece of JavaScript that knows how to draw common chart types (lines, bars, scatter plots) on a webpage. Without one, you'd have to draw every line and label by hand. We use [Chart.js v4](https://www.chartjs.org/) — it's free, popular, and handles most of what we need out of the box.

A **CDN** (Content Delivery Network) is a public hosting service for common code libraries. Instead of downloading Chart.js and bundling it into our project, we point the HTML at a CDN URL and the browser fetches it on page load. This keeps our file small and means the library updates itself when the CDN does. The trade-off: the dashboard needs internet on first load (browsers cache it after).

The custom `eventLines` plugin (the vertical reference lines for COVID, bike change, etc.) is defined inline in the HTML — Chart.js lets you write small extensions for behavior the library doesn't ship with.

### How big is the dashboard file? When would I switch to a database?

About **372 KB** with all data inlined — plenty small to email or host on GitHub Pages.

The "graduate to a database" thresholds from the dashboard article all apply here:

- **File size becomes painful.** A self-contained HTML up to a few MB still loads fast in a browser. Once you're north of ~5 MB you'll start to notice — that's roughly when an embedded JSON gets unwieldy. We're at 0.4 MB so we're nowhere close.
- **You want to query, not just display.** A database makes sense when you want to ask ad-hoc questions ("what was my best 60-min ride in 2022?") without rewriting the organize script. Right now we'd have to add a new aggregation in Python.
- **Multiple data sources need to combine.** If you wanted to layer in Apple Health (which we have in the original zip but didn't use), or Strava, or sleep data — joining them in JSON gets messy fast. A database with proper tables is much cleaner.
- **Frequent automated refreshes.** If you wanted the dashboard to refresh nightly from a cron job, writing/reading from PostgreSQL is more robust than rewriting a JSON file every night.

For your single-user, single-source, monthly-refresh Peloton dashboard? JSON is the right call. You'd consider PostgreSQL if you start pulling in Apple Health and want one combined fitness dashboard.

## See also

- [DATA_MODEL.md](./DATA_MODEL.md) — full schema reference for `dashboard_data.json` with ERD

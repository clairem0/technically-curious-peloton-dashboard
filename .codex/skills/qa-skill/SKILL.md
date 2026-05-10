---
name: qa-skill
description: Run QA for the Peloton dashboard after data refreshes or UI edits. Use when asked to sanity-check the dashboard, compare rendered totals against organized/dashboard_data.json and raw_data/peloton_workouts.csv, verify the baked HTML data, walk the local browser UI, or confirm raw Peloton exports are not committed.
---

# Peloton Dashboard QA

Use this skill from the `peloton-dashboard` repo root.

## Workflow

1. Confirm repo state:
   ```bash
   git branch --show-current
   git status --short --ignored=matching raw_data/workouts_raw.csv
   ```

2. Run deterministic data checks:
   ```bash
   python3 .codex/skills/qa-skill/scripts/verify_dashboard.py --repo .
   ```

3. Open or reload the static dashboard in the in-app browser:
   ```text
   file://<absolute repo path>/dashboard/dashboard.html
   ```
   Derive the absolute repo path from `pwd`; do not hard-code a local username.

4. Compare the visible UI to the script's `Expected visible totals`:
   - data-through copy in the masthead
   - headline stats: active-week streak, core workouts, performance rides, training hours
   - volume cards: training hours, reported miles, estimated calories, core workouts, ancillary footnote
   - instructor counts, especially the top row

5. Walk the interaction surface:
   - Volume controls switch between Hours, Workouts, Miles, and Calories without blank charts or console errors.
   - Consistency heatmap renders with Sunday-Saturday day labels aligned to rows and scrolls horizontally on narrow viewports.
   - Power trend controls show PZ Endurance, PZ Standard, PZ Max, and FTP Test.
   - Duration controls update for the selected ride type.
   - FTP Test shows discrete benchmark points rather than a rolling line.
   - Event markers appear on power charts; context markers can appear on volume charts.
   - PNG export buttons are visible. Test an export only if explicitly requested.

6. Check browser console warnings/errors when using the Browser plugin:
   ```js
   await tab.dev.logs({ levels: ["error", "warn"], limit: 20 })
   ```

7. Report:
   - PASS/FAIL for browser rendering, visible totals, embedded JSON, CSV recompute, and privacy guardrails.
   - Any mismatches with exact displayed value, JSON value, and recomputed CSV value.
   - Whether `raw_data/workouts_raw.csv` is ignored and untracked.

## Guardrails

- Never stage or commit `raw_data/workouts_raw.csv`.
- Do not force-add ignored raw exports.
- Treat `git diff --check` trailing-whitespace warnings in `raw_data/peloton_workouts.csv` as a known CRLF artifact unless the file format changes unexpectedly.
- Keep calculations grounded in `organized/organize.py` and `DATA_MODEL.md`; do not invent alternate metric definitions during QA.

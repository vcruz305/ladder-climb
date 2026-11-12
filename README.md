# Ladder Climb

**An agent-first live ladder-climb leaderboard and atomic multi-agent benchmark harness.**

Ladder Climb v0.2.1 records independent optimization campaigns for multiple models, with live telemetry, immutable campaign archives, adversarial review verdicts, and searchable cross-model history. The CLI and HTTP server use only the Python standard library; the dashboard is plain HTML, CSS, JavaScript, and SVG.

- **Independent model locks** — each model has its own read-modify-write lock and atomic JSON feed.
- **Legacy compatible** — an existing `DIR/ladder.json` remains a single-board workspace; v1 `rung`/`notes` and metric aliases load transparently.
- **Experiment lifecycle** — atomic unique claims, `testing` → `kept`/`rejected`/`interrupted`, protected terminal timing, monotonic revisions, and independent `pending`/`verified`/`flagged` review.
- **History** — campaign archives, champion deltas, filtering, stable pagination, and full-result JSON/CSV exports with spreadsheet-formula neutralization.
- **Local-first security** — localhost binding and no CORS by default, CSP and no-cache headers, optional explicit LAN/CORS and bearer-token settings.

## Quick start

```sh
pip install ladder-climb
ladder demo --dir /tmp/my-ladder --serve
```

The synthetic demo creates three models: two simultaneous active climbs and one model with an archived Wave-1 campaign. For a checkout, use `PYTHONPATH=src python3 -m ladder_climb` in place of `ladder`.

The server defaults to `127.0.0.1`. Only on a trusted network, opt in explicitly:

```sh
ladder serve --dir ./climb --host 0.0.0.0 --port 18999 --cors
```

## Legacy single-board mode

Track syntax is `ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]`.

```sh
ladder init --dir ./climb --title "Inference Optimization" \
  --track 'prefill:Prompt Prefill:prefill tok/s:120:1000:higher' \
  --track 'latency:Request Latency:ms p50:90:35:lower'
ladder claim --dir ./climb --track prefill --prefix P
ladder rung --dir ./climb --track prefill --id P-001 --status kept \
  --value 284.9 --gate pass --metric relative_error=0.0004
ladder status --dir ./climb
ladder validate --dir ./climb
```

A duplicate `testing` claim or terminal overwrite is rejected. A legitimate explicit update uses `--expected-revision N`; `--force-update` is reserved for deliberate repair. Terminal `ended_at` and `duration_s` remain immutable during review or metadata updates. Interrupted attempts need no invented measurement.

## Multi-model workspace

```sh
ladder init --dir ./workspace --model atlas --model-name "Atlas 27B" \
  --hardware "Workstation" --title "Atlas Optimization" \
  --track 'decode:Decode:decode tok/s:18:90:higher'
ladder init --dir ./workspace --model mosaic --model-name "Mosaic 16B" \
  --title "Mosaic Optimization" \
  --track 'decode:Decode:decode tok/s:20:100:higher'
ladder models list --dir ./workspace --json
ladder serve --dir ./workspace
```

The layout is `workspace.json`, `models/MODEL_ID/ladder.json`, independent `models/MODEL_ID/ladder.lock`, and immutable `models/MODEL_ID/campaigns/CAMPAIGN_ID/{ladder.json,manifest.json}` archives. Never reinterpret or hand-edit these files.

Claim and record worker metadata:

```sh
ladder claim --dir ./workspace --model atlas --track decode --prefix D \
  --wave wave-2 --session session-7 --agent worker-3 --json
ladder review --dir ./workspace --model atlas --track decode --id D-001 \
  --review verified --reviewer verifier-1 --notes "All correctness fixtures pass" \
  --expected-revision 4
ladder archive --dir ./workspace --model atlas --campaign wave-2 --title "Wave 2"
ladder campaigns list --dir ./workspace --model atlas --json
```

All mutation commands accept a bounded `--lock-timeout` (10 seconds by default). Model locks are independent, so simultaneous model writers do not serialize against one another.

## Dashboard workflows

The dock and all history views are served from the same local dashboard; use these URLs directly or click the corresponding tabs:

- **Two-line model dock** — every `.model-dock` model tab keeps a live status beacon and testing indicator on its first line, plus inline per-track champion values/units and the model's rung count on its second line. Switching into Fleet or a history view does not hide sibling climbs, so live status remains visible across the workspace.
- **Fleet matrix** (`/?view=overview`) — the `Fleet (N)` tab lays models out side by side. Each card includes live mini worker strips and stepped-frontier sparklines for every track, with current champion/gain labels and archive/rung metadata. Select a card to open that model's live ladder.
- **Model History** (`/?model=MODEL_ID&view=history`) — browse clickable Active Climb and immutable campaign/wave archive cards, search and filter the selected campaign, and inspect the four-cell milestone summary (baseline-to-best, kept/explored hit rate, total climb time, and review/gate/archive totals). On the Active Climb, **Overlay Archives** loads every archived feed and draws each archive frontier as a dashed ghost line behind the live frontier for direct campaign comparison. Add `&campaign=ARCHIVE_ID` to link directly to one archive.
- **All History** (`/?view=global`) — search across rungs, commits, and metrics, then filter by model, status, and review verdict. Results support stable incremental loading and expandable metadata rows. **Export JSON** and **Export CSV** preserve the active server-side filters and export the full result set, not only loaded rows; CSV cells are neutralized against spreadsheet formula execution.

## History and export

```sh
ladder history --dir ./workspace --model atlas --status kept --review verified --json
ladder history --dir ./workspace --search "cache" --sort chronological
ladder export --dir ./workspace --format csv --output history.csv
ladder export --dir ./workspace --format json --track decode
```

Filters include model, campaign, track, status, gate, review, session, wave, date range, and full-text search. CSV cells beginning `=`, `+`, `-`, or `@` are neutralized.

## HTTP API

| Route | Purpose |
| --- | --- |
| `/`, `/assets/*` | Overview, per-model live/history, and global history UI |
| `/ladder.json` | Legacy feed or explicitly selected/default model only |
| `/api/health` | Health, revision, counts, and server time |
| `/api/workspace` | Side-by-side model cards and archive metadata |
| `/api/models/{id}/ladder.json?campaign=...` | Active or archived model feed |
| `/api/models/{id}/campaigns` | Campaign listing |
| `/api/history?...` | Server-filtered, paginated cross-model history |
| `/api/export?format=json\|csv&...` | Full server-filtered export |

Responses include CSP, no-cache, and nosniff headers. CORS is absent unless `--cors` is supplied. `--token` requires bearer authentication. The server is read-only; all mutations use locked CLI/store operations.

## Agent integration and development

Read **[AGENTS.md](AGENTS.md)**, **[CLAUDE.md](CLAUDE.md)**, and **[.hermes/skills/ladder-climb/SKILL.md](.hermes/skills/ladder-climb/SKILL.md)** before dispatching workers. Copy [templates/subagent-brief.md](templates/subagent-brief.md) for isolated workers.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The suite covers concurrent writers, independent model locks, init races, duplicate/revision protection, terminal timing, immutable archives, v1 aliases, workspace/history/export APIs, CSV injection defense, and public-content terminology hygiene.

## License

MIT. See [LICENSE](LICENSE).

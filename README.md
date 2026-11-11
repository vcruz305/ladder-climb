# Ladder Climb

**An agent-first live hill-climb leaderboard and atomic multi-agent benchmark harness.**

Ladder Climb gives autonomous workers one shared, corruption-resistant experiment ledger and a polished web UI. It supports any number of optimization tracks, either optimization direction, live attempt timers, arbitrary secondary metrics, correctness gates, and a newest-first activity stream. The server and CLI use only the Python standard library; the dashboard uses plain HTML, CSS, JavaScript, and SVG.

- **Zero runtime dependencies** — Python 3.10+ is enough.
- **Atomic writes** — an interprocess file lock protects each read-modify-write, then `os.replace` publishes the new JSON.
- **Parallel-agent native** — log an attempt before benchmarking and its outcome afterward, even from separate worktrees.
- **Any objective** — throughput, latency, binary size, quality, cost, or custom units; `higher` and `lower` directions are first-class.
- **Live, responsive UI** — 2-second polling, per-track KPIs and trajectories, target progress, mobile cards, and timezone selection.
- **Local-first** — no accounts, cookies, analytics, CDN assets, or external telemetry.

## Quick start

Preview a synthetic three-track GPU optimization campaign:

```sh
uvx --from ladder-climb ladder demo --dir /tmp/my-ladder --serve
```

Or install and run explicitly:

```sh
pip install ladder-climb
ladder demo --dir /tmp/my-ladder --serve
```

Other equivalent entry points:

```sh
pipx run --spec ladder-climb ladder demo --dir /tmp/my-ladder --serve
python3 -m ladder_climb demo --dir /tmp/my-ladder --serve
```

Open the printed localhost URL. When bound to `0.0.0.0`, the server also prints detected LAN and tailnet URLs. Only expose it on networks you trust.

For a source checkout:

```sh
python3 -m pip install -e .
ladder --help
```

You can also run without installation by setting `PYTHONPATH=src`.

## Initialize a campaign

Track syntax is:

```text
ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]
```

The direction defaults to `higher`. Quote the whole specification so spaces remain intact.

```sh
ladder init \
  --dir ./climb \
  --title "Inference Optimization" \
  --subtitle "Parallel workers · correctness gated" \
  --track 'prefill:Prompt Prefill:prefill tok/s:120:1000:higher' \
  --track 'decode:Spec Decode:decode tok/s:18:90:higher' \
  --track 'latency:Request Latency:ms p50:90:35:lower'

ladder serve --dir ./climb --host 0.0.0.0 --port 18999
```

Every campaign needs at least one track; there is no fixed upper limit imposed by the UI.

## Log attempts

Log `testing` **before** starting the benchmark so the dashboard timer ticks while the worker runs:

```sh
ladder rung --dir ./climb --track prefill --id P-042 \
  --status testing --value 0 --summary "Fuse unpack into the tile loop" \
  --commit 9f31ac2 --gate pending --metric batch_tokens=1024
```

Finish with `kept` or `rejected`. The CLI preserves the original start timestamp and computes `duration_s` automatically:

```sh
ladder rung --dir ./climb --track prefill --id P-042 \
  --status kept --value 284.9 --gate pass \
  --metric relative_error=0.0004 --metric median_runs=5
```

If the change loses, revert the code but keep the rejected ledger entry:

```sh
ladder rung --dir ./climb --track prefill --id P-043 \
  --status rejected --value 241.2 --summary "Wider tiles reduce occupancy" \
  --gate pass --metric occupancy=0.37
```

Use `--duration-s` to supply an externally measured duration. `--parity` is an alias for `--gate`. Additional `--metric KEY=VAL` flags accept JSON values (numbers, booleans, arrays, objects, quoted strings) or plain strings.

**Never write `ladder.json` directly. Always use `ladder rung`.** A board's lock covers both reading and replacing the feed, so independent processes cannot lose one another's updates.

## Inspect and validate

```sh
ladder status --dir ./climb
ladder status --dir ./climb --json
ladder validate --dir ./climb
```

`status` prints champions, baselines, targets, kept/explored counts, and live attempts. `validate` checks types, finite values, track/rung IDs, status values, units, timestamps, non-negative durations, correctness gates, duplicate IDs, and chronological champion monotonicity.

## HTTP endpoints

| Route | Purpose |
| --- | --- |
| `/` | Live dashboard |
| `/ladder.json` | Complete public board feed |
| `/api/health` | Schema version, track/rung counts, update timestamp |
| `/assets/*` | Self-contained dashboard assets |

All responses disable caching. The feed allows cross-origin reads so a file-opened dashboard can poll a local server. The server has no write endpoint; benchmark state changes only through the locked CLI.

## JSON contract

```json
{
  "schema_version": 1,
  "title": "Inference Optimization",
  "subtitle": "Parallel workers",
  "created_at": "2026-01-01T00:00:00.000Z",
  "updated_at": "2026-01-01T00:04:00.000Z",
  "tracks": {
    "prefill": {
      "label": "Prompt Prefill",
      "unit": "prefill tok/s",
      "baseline": 120.0,
      "target": 1000.0,
      "direction": "higher",
      "rungs": [{
        "id": "P-042",
        "status": "kept",
        "value": 284.9,
        "unit": "prefill tok/s",
        "summary": "Fuse unpack into the tile loop",
        "commit": "9f31ac2",
        "gate": "pass",
        "metrics": {"relative_error": 0.0004},
        "started_at": "2026-01-01T00:00:00.000Z",
        "updated_at": "2026-01-01T00:04:00.000Z",
        "duration_s": 240.0
      }]
    }
  }
}
```

Statuses are `testing`, `kept`, `rejected`, and `baseline`. Baseline/target values may be `null`. A kept rung must have a passing gate and cannot regress the current champion. Rejected attempts can carry any measured value and either gate outcome.

## Agent and harness integration

Read **[.hermes/skills/ladder-climb/SKILL.md](.hermes/skills/ladder-climb/SKILL.md)** for the complete operator contract. It includes isolated-worktree orchestration, paired benchmark gates, lock discipline, failure handling, and completion criteria. Hermes Agent users can install or symlink that directory as a profile skill; other agent harnesses can import the same Markdown instructions. Copy `templates/subagent-brief.md` when dispatching parallel workers.

The minimal loop is:

1. Initialize and validate a board; start the server.
2. Give each worker an isolated worktree, a unique rung-ID prefix, and an explicit hardware lock if needed.
3. Log `testing` before each benchmark.
4. Run correctness checks and paired baseline/candidate/baseline measurements.
5. Keep winners, revert losers, and atomically log either outcome.
6. Validate the final board and leave no unexplained `testing` rungs.

## Development

```sh
python3 -m unittest discover -s tests -v
```

The tests exercise concurrent subprocess writers, automatic durations, both optimization directions, schema validation, HTTP responses, and repository public-content hygiene. CI runs the same zero-dependency suite on Python 3.11 and 3.12.

## License

MIT. See [LICENSE](LICENSE).

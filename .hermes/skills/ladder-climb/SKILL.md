---
name: ladder-climb
description: Use when ladder-climbing benchmarks with parallel agents. Maintain independent atomic model ledgers, history, and review.
---

# Ladder Climb

Run measurable optimization campaigns with corruption-resistant ledgers. Read the repository `AGENTS.md` for the full operator contract.

## Initialize and serve

Confirm objectives, correctness criteria, baselines, directions, and units. Plain directories remain legacy single boards. For simultaneous models, initialize each independently:

```sh
ladder init --dir BOARD --model MODEL_ID --model-name DISPLAY_NAME \
  --title TITLE --hardware HARDWARE \
  --track 'speed:Kernel Speed:tok/s:100:500:higher' \
  --track 'latency:Request Latency:ms:80:30:lower'
ladder validate --dir BOARD --model MODEL_ID
ladder models list --dir BOARD --json
```

Start `ladder serve --dir BOARD`. Binding defaults to localhost. Only use `--host 0.0.0.0 --cors` on an explicitly trusted network; consider `--token` for shared access.

Each model uses `models/MODEL_ID/ladder.lock`; different models never share a mutation lock. Never reinterpret an existing legacy directory as a workspace implicitly.

## Required worker loop

Read prior kept and rejected rungs first. Claim a unique ID atomically rather than predicting one:

```sh
ladder claim --dir BOARD --model MODEL_ID --track speed --prefix SPEED \
  --wave wave-2 --session SESSION --agent AGENT --json
```

The claim creates `testing` before benchmarking. If using explicit IDs, create with `ladder rung ... --status testing --value 0 --gate pending`. Use A → B → A paired measurements when noise can affect results and run correctness checks before promotion.

Finish the same ID with `kept`, `rejected`, or `interrupted`:

```sh
ladder rung --dir BOARD --model MODEL_ID --track speed --id SPEED-001 \
  --status kept --value 184.2 --gate pass --metric output_delta=0.0001
ladder rung --dir BOARD --model MODEL_ID --track speed --id SPEED-002 \
  --status interrupted --reason 'Worker crashed before measurement'
```

Never invent a value to close a crashed attempt. Terminal `ended_at` and `duration_s` are preserved. Negative clock skew is flagged rather than clamped to a fictitious zero.

Duplicate testing claims and accidental terminal overwrites fail. Explicit updates require the current board `--expected-revision N`; on conflict, reload and reconcile instead of retrying blindly. `--force-update` is only for deliberate repair. All lock waits have bounded `--lock-timeout` (default 10 seconds).

## Independent adversarial review

Gate evidence and review verdict are separate. A correctness pass is not automatically an adversarial verification:

```sh
ladder review --dir BOARD --model MODEL_ID --track speed --id SPEED-001 \
  --review verified --reviewer REVIEWER --notes 'Evidence checked' --expected-revision N
```

Use `pending`, `verified`, or `flagged`. Review must never silently change kept/rejected status. Record concrete review notes and preserve gate evidence.

## Archives and history

Snapshot completed waves into immutable per-model archives:

```sh
ladder archive --dir BOARD --model MODEL_ID --campaign wave-1 --title 'Wave 1'
ladder campaigns list --dir BOARD --model MODEL_ID --json
ladder history --dir BOARD --model MODEL_ID --review verified --json
ladder export --dir BOARD --format csv --output history.csv
```

Use `--start-next` only when intentionally starting an empty successor campaign. Never mutate archived `ladder.json` files. Global history supports search, model/campaign/track/status/gate/review/session/wave filters, chronological replay, pagination, and JSON/CSV export.

## Safety invariants

- Never edit `ladder.json` directly; use locked store/CLI mutations and atomic replacement.
- Do not delete lock files during campaigns. Use filesystems with reliable `fcntl.flock` semantics.
- Isolate coding workers and explicitly reserve contended benchmark hardware. Model board locks do not replace hardware locks.
- Keep units, directions, and benchmark regimes separate across models; do not declare global champions from incomparable tracks.
- Resolve or explain every testing rung, validate each model, and report champion values/units, commits, gains, gates, review verdicts, and remaining limitations.

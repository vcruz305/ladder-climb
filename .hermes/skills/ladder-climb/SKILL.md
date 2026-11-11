---
name: ladder-climb
description: Use when hill-climbing benchmarks with parallel agents. Maintain an atomic live leaderboard.
---

# Ladder Climb

Run measurable optimization campaigns with a shared, lock-protected ledger. This skill works for autonomous orchestrators and isolated benchmark workers.

## Start a campaign

When asked to hill-climb an objective or run a live optimization campaign:

1. Confirm objectives, correctness criteria, baselines, and units. Use a separate track per objective and `lower` for latency, size, cost, or error.
2. Initialize and validate the board:

```sh
ladder init --dir BOARD --title TITLE --subtitle SUBTITLE \
  --track 'speed:Kernel Speed:tok/s:100:500:higher' \
  --track 'latency:Request Latency:ms:80:30:lower'
ladder validate --dir BOARD
```

3. Start `ladder serve --dir BOARD --host 0.0.0.0 --port 18999` and give the user the dashboard URL.
4. Read existing kept and rejected rungs before choosing a hypothesis. Never repeat a documented dead end.
5. Give parallel workers isolated worktrees, unique rung prefixes, and explicit exclusive-resource reservations. All workers share BOARD.

Preview the UI with `ladder demo --dir DEMO_DIR --serve`.

## Required worker loop

Log the attempt **before** benchmarking:

```sh
ladder rung --dir BOARD --track speed --id SPEED-017 \
  --status testing --value 0 --commit COMMIT --gate pending \
  --summary 'Hypothesis and configuration' --metric warmup=3
```

Use A → B → A paired measurements when noise can affect the result. Keep inputs and benchmark conditions comparable. Run correctness checks before promotion and record numeric evidence in `--metric` flags.

Keep a winner only after preserving its exact source:

```sh
ladder rung --dir BOARD --track speed --id SPEED-017 \
  --status kept --value 184.2 --gate pass \
  --summary 'Hypothesis and measured evidence' --metric output_delta=0.0001
```

Revert a loser from integration but preserve its ledger entry:

```sh
ladder rung --dir BOARD --track speed --id SPEED-018 \
  --status rejected --value 91.7 --gate pass \
  --summary 'Why the hypothesis failed'
```

Completion computes `duration_s` from `started_at` unless `--duration-s` is given. `--parity` aliases `--gate`. An interrupted attempt must stay truthful; never invent measurements.

## Locking and integration invariants

- Never edit `ladder.json` directly; every mutation goes through `ladder rung`.
- The CLI holds `fcntl.flock` across the full read-modify-write transaction and uses `os.replace` to publish complete JSON.
- Do not delete `ladder.lock` during a campaign. Use a local filesystem with reliable locks.
- Use at most one benchmark worker per contended exclusive device. Reviews and non-benchmark tasks can run independently.
- Rebase workers after integrating a winner and rerun gates when integration changes the result.
- A kept rung must pass its gate and cannot regress the existing champion.

## Monitor and finish

Use `ladder status --dir BOARD` to inspect champions and active attempts; `--json` provides the full feed. Do not trust terminal output without checking the board.

At completion, resolve or explain every `testing` rung, run `ladder validate --dir BOARD`, and report each champion, unit, gain, winning commit, gate evidence, kept/rejected counts, and remaining limitations. Preserve inconclusive and failed attempts as search-space knowledge.

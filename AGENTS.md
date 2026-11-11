# Ladder Climb — Agent Operator Entry Point

For any request to run an optimization campaign, benchmark ladder-climb, or multi-agent leaderboard, read this file and [`.hermes/skills/ladder-climb/SKILL.md`](.hermes/skills/ladder-climb/SKILL.md) before launching workers.

A target codebase, one or more measurable metrics, and a correctness gate are sufficient user input; you own board initialization, server startup, worktree partitioning, exclusive hardware locking, paired A/B verification, and live rung streaming. Do not ask the user to hand-edit JSON or paste boilerplate commands.

## 1. Zero-Ceremony Campaign Startup

1. **Install or invoke directly** (Python 3.10+ stdlib only — zero runtime dependencies):
   ```sh
   python3 -m pip install -e /path/to/ladder-climb
   # or without installing:
   PYTHONPATH=/path/to/ladder-climb/src python3 -m ladder_climb --help
   ```
2. **Initialize the board** with one `--track` per metric (`ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]`, where `DIRECTION` is `higher` or `lower`):
   ```sh
   ladder init \
     --dir "$BOARD_DIR" \
     --title "Kernel Optimization Campaign" \
     --subtitle "Parallel workers · correctness gated" \
     --track 'prefill:Prompt Prefill:prefill tok/s:120:1000:higher' \
     --track 'decode:Spec Decode:decode tok/s:18:90:higher'
   ladder validate --dir "$BOARD_DIR"
   ```
3. **Start the live dashboard server** (`127.0.0.1` by default; pass `--host 0.0.0.0` explicitly on trusted LAN/Tailscale networks):
   ```sh
   ladder serve --dir "$BOARD_DIR" --host 0.0.0.0 --port 18999
   ```
   Report the printed localhost / LAN / Tailscale URLs immediately.

### Running Multiple Model Ladder Climbs Simultaneously (Workspace Mode)

To run and monitor several independent model ladder climbs at the same time under one shared server and UI, pass `--model MODEL_ID` (`each model gets its own independent `models/MODEL_ID/ladder.lock` so concurrent teams never contend`):

```sh
ladder init --dir "$WORKSPACE_DIR" --model qwen27b --model-name "27B Dense+GDN (M5 Max)" \
  --title "27B Ladder Climb" \
  --track 'prefill:Prompt Prefill:prefill tok/s:120:1000:higher' \
  --track 'decode:Spec Decode:decode tok/s:18:90:higher'

ladder init --dir "$WORKSPACE_DIR" --model moe16b --model-name "16B MoE Flash" \
  --title "16B MoE Ladder Climb" \
  --track 'decode:Spec Decode:decode tok/s:45:110:higher'

ladder models list --dir "$WORKSPACE_DIR" --json
ladder serve --dir "$WORKSPACE_DIR" --host 0.0.0.0 --port 18999
```

Workers target their assigned model via `--model MODEL_ID`, can atomically claim unique rung IDs (`ladder claim --dir "$WORKSPACE_DIR" --model qwen27b --track decode --prefix D`), attach `--wave` / `--session` / `--agent` metadata, record independent verifier verdicts (`ladder review --dir "$WORKSPACE_DIR" --model qwen27b --track decode --id D-007 --review verified --reviewer verifier-1 --notes "320/320 exact"`), snapshot finished waves into immutable per-model history (`ladder archive --dir "$WORKSPACE_DIR" --model qwen27b --campaign wave-1`), and query/export cross-model or per-model history (`ladder history --dir "$WORKSPACE_DIR"` / `ladder export --dir "$WORKSPACE_DIR" --format csv`).

## 2. Mandatory Worker Loop (`testing` -> `kept` | `rejected`)

Every benchmark worker — whether single-agent or parallel subagents in isolated `git worktree` checkouts — MUST execute this state transition on every rung:

1. **Read prior rungs first** (`ladder status --dir "$BOARD_DIR" --json`) so no worker repeats an already-tested dead end.
2. **Log `testing` BEFORE starting the benchmark** so the live elapsed timer ticks on the dashboard while the run executes:
   ```sh
   ladder rung --dir "$BOARD_DIR" --track prefill --id P-014 \
     --status testing --value 0 --commit "$(git rev-parse --short HEAD)" \
     --gate pending --summary "Contiguous [N/BN, K, BN] weight panels"
   ```
3. **Enforce correctness gates and paired A/B discipline:**
   - Compile outside any shared GPU/device lock; acquire the exclusive hardware lock (`flock` / `lockf`) only around actual hardware test and benchmark runs.
   - Use paired `A -> B -> A` (or `B -> A -> B`) interleaved runs whenever thermal or system drift can affect measurements.
   - Verify exactness / numerical parity gates (`0` ULP, `relRMS` threshold, test suite pass) BEFORE marking a rung `kept`.
4. **Commit winners and mark `kept`** (`duration_s` is computed automatically from `started_at` unless `--duration-s` is supplied):
   ```sh
   ladder rung --dir "$BOARD_DIR" --track prefill --id P-014 \
     --status kept --value 925.1 --commit "$(git rev-parse --short HEAD)" \
     --gate "relRMS=1.63e-3 PASS" \
     --summary "Contiguous weight panels cut K-stride jumps" \
     --metric m512_tps=827.7 --metric m2048_tps=847.3
   ```
5. **Revert losers in git, but ALWAYS record `rejected` on the board:**
   ```sh
   ladder rung --dir "$BOARD_DIR" --track prefill --id P-015 \
     --status rejected --value 880.9 --gate "relRMS=1.63e-3 PASS" \
     --summary "Concurrent unpack/GEMM overlap regressed SLC locality; reverted"
   ```
   Rejected rungs are first-class search-space memory for sibling and future agents.

## 3. Multi-Agent Safety Invariants

- **Never write or overwrite `ladder.json` directly.** Every state change MUST go through `ladder rung`, which acquires an exclusive `fcntl.flock` on `ladder.lock` across the entire read-validate-write transaction and publishes via atomic `os.replace`.
- **Never delete `ladder.lock`** while workers may be active.
- **Partition parallel subagents cleanly** using [`templates/subagent-brief.md`](templates/subagent-brief.md):
  - One isolated `git worktree` and per-worktree build target directory per coding worker.
  - Distinct rung ID prefixes per track (`P-*`, `D-*`, `LAT-*`).
  - One shared lock file serializing exclusive benchmark hardware.
- **Validate before concluding:** run `ladder validate --dir "$BOARD_DIR"` and `ladder status --dir "$BOARD_DIR"` at every check-in and before final handoff, ensuring no abandoned `testing` rungs remain unresolved.

## 4. Repository Development & Verification

Run the zero-dependency test suite (including 8-process concurrent lock stress tests, schema invariants, demo validation, and repository hygiene checks) before every commit:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

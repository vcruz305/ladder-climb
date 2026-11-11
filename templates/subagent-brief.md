# Parallel Hill-Climb Worker Brief

Copy this brief into a worker task and fill every placeholder. One worker owns one hypothesis at a time.

## Assignment

- **Objective / track:** `TRACK_ID — TRACK_LABEL (UNIT, DIRECTION is better)`
- **Hypothesis:** `ONE INDEPENDENT CHANGE AND WHY IT SHOULD HELP`
- **Worker rung prefix:** `UNIQUE_PREFIX`
- **Source worktree:** `ISOLATED_WORKTREE`
- **Shared board directory:** `BOARD_DIR`
- **Starting champion commit:** `COMMIT_SHA`
- **Exclusive resource reservation:** `RESOURCE_OR_NONE`
- **Benchmark command:** `EXACT_COMMAND`
- **Correctness gate and tolerance:** `EXACT_COMMAND_AND_THRESHOLD`
- **Minimum improvement / noise threshold:** `THRESHOLD`
- **Attempt budget / stopping condition:** `BUDGET`

## Required procedure

1. Read the current board with `ladder status --dir BOARD_DIR --json`; review rejected rungs to avoid duplicate dead ends.
2. Confirm the worktree matches the assigned champion and no unrelated changes are present. Do not touch another worker's worktree.
3. Choose a unique rung ID with your prefix. Log `testing` **before** benchmarking:

   ```sh
   ladder rung --dir BOARD_DIR --track TRACK_ID --id UNIQUE_RUNG_ID \
     --status testing --value 0 --commit CANDIDATE_COMMIT --gate pending \
     --summary 'Hypothesis and exact configuration' \
     --metric warmup=3 --metric repetitions=5
   ```

4. Implement only the assigned hypothesis. Preserve build artifacts and logs needed to reproduce the measurement.
5. Run the correctness gate. Run paired A → B → A benchmarks when noise matters, using identical inputs and conditions. Record medians and dispersion, not a cherry-picked best sample.
6. If the result wins by the required threshold and every gate passes, preserve/commit the exact winning source and mark it `kept`:

   ```sh
   ladder rung --dir BOARD_DIR --track TRACK_ID --id UNIQUE_RUNG_ID \
     --status kept --value MEASURED_VALUE --gate pass \
     --summary 'Result and key evidence' --metric output_delta=NUMBER
   ```

7. If it loses or fails, revert the candidate from the integration path, keep the evidence, and mark the same rung `rejected` with the truthful gate outcome and measured value. Explain why in the summary.
8. Omit `--duration-s` to derive duration from the testing timestamp. Add structured `--metric KEY=VAL` flags for shapes, noise, errors, memory, and benchmark settings.
9. Run `ladder validate --dir BOARD_DIR` and report your final rung, value, unit, gate evidence, source commit, and remaining risks.

## Hard rules

- Never edit `ladder.json` directly. All state changes go through `ladder rung`.
- Never reuse a rung ID for a different experiment.
- Never hold an exclusive benchmark resource while doing unrelated work.
- Never mark a regression `kept`, bypass a correctness gate, or invent missing measurements.
- If interrupted, report the active `testing` rung explicitly; finish it as `rejected` with an interruption explanation when appropriate.
- After another worker integrates a winner, rebase before the next attempt and rerun correctness checks.

## Return report

- Rung ID and final status
- Measured value and unit; prior and new champion
- Gate results and secondary metrics
- Winning commit, or confirmation that loser code was reverted
- Benchmark conditions and noise observations
- Recommended next hypothesis, if any
- `ladder validate` result and unresolved issues

# Claude Code Instructions

Read and follow [`AGENTS.md`](AGENTS.md) and [`.hermes/skills/ladder-climb/SKILL.md`](.hermes/skills/ladder-climb/SKILL.md) as the authoritative operator and development contract for this repository.

## Quick Commands

- Run full test suite: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- Launch interactive demo board: `PYTHONPATH=src python3 -m ladder_climb demo --dir /tmp/ladder-demo --serve`
- Initialize a campaign: `ladder init --dir ./climb --title "Campaign" --track 'main:Throughput:tok/s:100:500:higher'`
- Record a rung atomically: `ladder rung --dir ./climb --track main --id R-01 --status testing --value 0 --summary "..."`
- Validate ledger integrity: `ladder validate --dir ./climb`

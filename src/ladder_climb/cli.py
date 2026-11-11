"""Command-line interface for legacy boards and multi-model workspaces."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Sequence
from . import __version__
from .demo import make_demo
from .history import export_history, history_payload
from .schema import STATUSES, ValidationError, champion, load_board, parse_time
from .server import serve
from .store import archive_campaign, claim_rung, initialize, list_campaigns, list_models, paths_for, review_rung, upsert_rung

def track_spec(text: str) -> dict[str, Any]:
    parts = text.split(":")
    if not 3 <= len(parts) <= 6: raise argparse.ArgumentTypeError("expected ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]")
    track_id, label, unit = (part.strip() for part in parts[:3])
    if not all((track_id, label, unit)): raise argparse.ArgumentTypeError("track id, label, and unit cannot be empty")
    optional = parts[3:] + [""] * (3 - len(parts[3:])); result = {"id": track_id, "label": label, "unit": unit}
    for key, raw in zip(("baseline", "target"), optional):
        try: result[key] = float(raw) if raw else None
        except ValueError as exc: raise argparse.ArgumentTypeError(f"{key} must be numeric") from exc
    result["direction"] = optional[2] or "higher"
    if result["direction"] not in ("higher", "lower"): raise argparse.ArgumentTypeError("direction must be higher or lower")
    return result

def metric_pair(text: str) -> tuple[str, Any]:
    if "=" not in text: raise argparse.ArgumentTypeError("metric must be KEY=VAL")
    key, raw = text.split("=", 1)
    if not key.strip(): raise argparse.ArgumentTypeError("metric key cannot be empty")
    try: value = json.loads(raw)
    except json.JSONDecodeError: value = raw
    return key.strip(), value

def _dir(p: argparse.ArgumentParser, model: bool = False, campaign: bool = False) -> None:
    p.add_argument("--dir", default=".")
    if model: p.add_argument("--model")
    if campaign: p.add_argument("--campaign")
def _json(p: argparse.ArgumentParser) -> None: p.add_argument("--json", action="store_true")
def _timeout(p: argparse.ArgumentParser) -> None: p.add_argument("--lock-timeout", type=float, default=10.0)
def _filters(p: argparse.ArgumentParser) -> None:
    for name in ("model", "campaign", "track", "status", "gate", "review", "search", "session", "wave", "since", "until"): p.add_argument("--" + name)
    p.add_argument("--sort", choices=("newest", "chronological"), default="newest")
    p.add_argument("--limit", type=int, default=500); p.add_argument("--offset", type=int, default=0)

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ladder", description="Atomic multi-agent ladder-climb leaderboard")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}"); commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); _dir(p, True); p.add_argument("--model-name"); p.add_argument("--hardware"); p.add_argument("--campaign-id")
    p.add_argument("--title", required=True); p.add_argument("--subtitle", default="Live optimization campaign")
    p.add_argument("--track", action="append", required=True, type=track_spec); p.add_argument("--force", action="store_true"); _timeout(p)
    p = commands.add_parser("rung"); _dir(p, True, True); p.add_argument("--track", required=True); p.add_argument("--id", required=True, dest="rung_id")
    p.add_argument("--value", type=float); p.add_argument("--status", required=True, choices=sorted(STATUSES)); p.add_argument("--unit"); p.add_argument("--commit")
    p.add_argument("--summary"); p.add_argument("--reason"); p.add_argument("--gate", "--parity", dest="gate"); p.add_argument("--duration-s", type=float)
    p.add_argument("--metric", action="append", default=[], type=metric_pair); p.add_argument("--wave"); p.add_argument("--session"); p.add_argument("--agent")
    p.add_argument("--expected-revision", type=int); p.add_argument("--force-update", action="store_true"); _timeout(p); _json(p)
    p = commands.add_parser("claim"); _dir(p, True); p.add_argument("--track", required=True); p.add_argument("--prefix", required=True)
    p.add_argument("--wave"); p.add_argument("--session"); p.add_argument("--agent"); _timeout(p); _json(p)
    p = commands.add_parser("review"); _dir(p, True); p.add_argument("--track", required=True); p.add_argument("--id", required=True, dest="rung_id")
    p.add_argument("--review", required=True, choices=("pending", "verified", "flagged")); p.add_argument("--reviewer"); p.add_argument("--notes")
    p.add_argument("--expected-revision", type=int); _timeout(p); _json(p)
    p = commands.add_parser("archive"); p.add_argument("--dir", default="."); p.add_argument("--model", required=True); p.add_argument("--campaign", required=True)
    p.add_argument("--title"); p.add_argument("--start-next", action="store_true"); _timeout(p); _json(p)
    p = commands.add_parser("models"); sub = p.add_subparsers(dest="subcommand", required=True); q = sub.add_parser("list"); _dir(q); _json(q)
    p = commands.add_parser("campaigns"); sub = p.add_subparsers(dest="subcommand", required=True); q = sub.add_parser("list"); _dir(q); q.add_argument("--model", required=True); _json(q)
    for name in ("status", "validate"):
        p = commands.add_parser(name); _dir(p, True, True)
        if name == "status": _json(p)
    p = commands.add_parser("history"); _dir(p); _filters(p); _json(p)
    p = commands.add_parser("export"); _dir(p); _filters(p); p.add_argument("--format", required=True, choices=("json", "csv")); p.add_argument("--output")
    p = commands.add_parser("serve"); _dir(p, True, True); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=18999)
    p.add_argument("--cors", action="store_true"); p.add_argument("--token")
    p = commands.add_parser("demo"); p.add_argument("--dir", required=True); p.add_argument("--serve", action="store_true")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=18999); p.add_argument("--cors", action="store_true")
    return root

def format_number(value: float | None) -> str: return "—" if value is None else f"{value:,.3f}".rstrip("0").rstrip(".")
def format_duration(seconds: float | None) -> str:
    if seconds is None: return "—"
    seconds = max(0, int(seconds))
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600: return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
def print_status(board: dict[str, Any]) -> None:
    print(f"\n{board['title']}\n{board['subtitle']}\n")
    for track_id, track in board["tracks"].items():
        best, winner = champion(track); rungs = track["rungs"]
        counts = {name: sum(r["status"] == name for r in rungs) for name in STATUSES}
        print(f"{track_id} · {track['label']}  [{track['direction']} is better]")
        print(f"  champion : {format_number(best)} {track['unit']}  ({winner['id'] if winner else 'metadata baseline'})")
        print(f"  baseline : {format_number(track['baseline'])} {track['unit']}   target: {format_number(track['target'])} {track['unit']}")
        print(f"  explored : {len(rungs)}   kept: {counts['kept']}   rejected: {counts['rejected']}   testing: {counts['testing']}")
        for rung in (r for r in rungs if r["status"] == "testing"):
            from datetime import datetime, timezone
            started = parse_time(rung["started_at"]); elapsed = (datetime.now(timezone.utc) - started).total_seconds() if started else None
            print(f"  LIVE     : {rung['id']} · {format_duration(elapsed)} · {rung['summary']}")
        print()
def _emit(value: Any, as_json: bool, text: str) -> None: print(json.dumps(value, indent=2, ensure_ascii=False) if as_json else text)
def _filter_args(args: argparse.Namespace) -> dict[str, Any]:
    return {k: getattr(args, k, None) for k in ("model", "campaign", "track", "status", "gate", "review", "search", "session", "wave", "since", "until", "sort")}

def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            board = initialize(args.dir, args.title, args.subtitle, args.track, force=args.force, model=args.model,
                model_name=args.model_name, hardware=args.hardware, campaign_id=args.campaign_id, lock_timeout=args.lock_timeout)
            print(f"Initialized {len(board['tracks'])} track(s) in {paths_for(args.dir, args.model).feed.parent}")
        elif args.command == "rung":
            summary = args.summary if args.summary is not None else args.reason
            rung = upsert_rung(args.dir, track=args.track, rung_id=args.rung_id, value=args.value, status=args.status,
                unit=args.unit, commit=args.commit, summary=summary, gate=args.gate, duration_s=args.duration_s, metrics=dict(args.metric),
                model=args.model, campaign=args.campaign, wave=args.wave, session=args.session, agent=args.agent,
                expected_revision=args.expected_revision, force_update=args.force_update, lock_timeout=args.lock_timeout)
            _emit(rung, args.json, f"{args.track}/{args.rung_id}: {args.status} · {format_number(rung.get('value'))} {rung['unit']} · {format_duration(rung.get('duration_s'))}")
        elif args.command == "claim":
            rung = claim_rung(args.dir, track=args.track, prefix=args.prefix, model=args.model, agent=args.agent, wave=args.wave,
                session=args.session, lock_timeout=args.lock_timeout); _emit(rung, args.json, f"{rung['id']} · revision {rung['revision']}")
        elif args.command == "review":
            rung = review_rung(args.dir, track=args.track, rung_id=args.rung_id, review=args.review, reviewer=args.reviewer,
                notes=args.notes, model=args.model, expected_revision=args.expected_revision, lock_timeout=args.lock_timeout)
            _emit(rung, args.json, f"{args.track}/{args.rung_id}: review {args.review}")
        elif args.command == "archive":
            result = archive_campaign(args.dir, model=args.model, campaign=args.campaign, title=args.title, start_next=args.start_next, lock_timeout=args.lock_timeout)
            _emit(result, args.json, f"Archived {args.model}/{args.campaign}")
        elif args.command == "models": _emit(list_models(args.dir), args.json, "\n".join(m["id"] for m in list_models(args.dir)))
        elif args.command == "campaigns": _emit(list_campaigns(args.dir, args.model), args.json, "\n".join(c["campaign_id"] for c in list_campaigns(args.dir, args.model)))
        elif args.command in ("status", "validate"):
            board = load_board(paths_for(args.dir, args.model, args.campaign).feed.parent); total = sum(len(t["rungs"]) for t in board["tracks"].values())
            if args.command == "validate": print(f"Valid: {len(board['tracks'])} track(s), {total} rung(s)")
            elif args.json: print(json.dumps(board, indent=2))
            else: print_status(board)
        elif args.command == "history":
            payload = history_payload(args.dir, _filter_args(args), limit=args.limit, offset=args.offset)
            if args.json: print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                for r in payload["rows"]: print(f"{r['model']}/{r['campaign']}/{r['track']}/{r['rung']}  {r['status']}  {r['value']} {r['unit']}  {r.get('summary') or ''}")
                print(f"{payload['total']} result(s)")
        elif args.command == "export":
            content, _ = export_history(args.dir, args.format, _filter_args(args))
            if args.output: Path(args.output).write_text(content, encoding="utf-8"); print(args.output)
            else: print(content, end="")
        elif args.command == "serve":
            board = load_board(paths_for(args.dir, args.model, args.campaign).feed.parent); print(f"{board['title']} · {board['subtitle']}")
            serve(args.dir, args.host, args.port, model=args.model, campaign=args.campaign, cors=args.cors, token=args.token)
        elif args.command == "demo":
            board = make_demo(args.dir); print(f"Demo ready: 3 models in {Path(args.dir).resolve()}")
            if args.serve: serve(args.dir, args.host, args.port, cors=args.cors)
        return 0
    except (ValidationError, OSError, TimeoutError, ValueError, KeyboardInterrupt) as exc:
        print("\nStopped." if isinstance(exc, KeyboardInterrupt) else f"ladder: {exc}", file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())

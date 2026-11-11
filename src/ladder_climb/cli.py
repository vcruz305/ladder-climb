"""The ladder command-line interface."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .demo import make_demo
from .schema import STATUSES, ValidationError, champion, load_board, parse_time
from .server import serve
from .store import initialize, upsert_rung


def track_spec(text: str) -> dict[str, Any]:
    """Parse ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]."""
    parts = text.split(":")
    if not 3 <= len(parts) <= 6:
        raise argparse.ArgumentTypeError("expected ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]")
    track_id, label, unit = (part.strip() for part in parts[:3])
    if not all((track_id, label, unit)):
        raise argparse.ArgumentTypeError("track id, label, and unit cannot be empty")
    optional = parts[3:] + [""] * (3 - len(parts[3:]))
    result: dict[str, Any] = {"id": track_id, "label": label, "unit": unit}
    for key, raw in zip(("baseline", "target"), optional):
        if raw:
            try:
                result[key] = float(raw)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"{key} must be numeric") from exc
        else:
            result[key] = None
    direction = optional[2] or "higher"
    if direction not in ("higher", "lower"):
        raise argparse.ArgumentTypeError("direction must be higher or lower")
    result["direction"] = direction
    return result


def metric_pair(text: str) -> tuple[str, Any]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("metric must be KEY=VAL")
    key, raw = text.split("=", 1)
    if not key.strip():
        raise argparse.ArgumentTypeError("metric key cannot be empty")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return key.strip(), value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ladder", description="Atomic multi-agent hill-climb leaderboard")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a board")
    init.add_argument("--dir", default=".")
    init.add_argument("--title", required=True)
    init.add_argument("--subtitle", default="Live optimization campaign")
    init.add_argument("--track", action="append", required=True, type=track_spec,
                      metavar="ID:LABEL:UNIT[:BASELINE[:TARGET[:DIRECTION]]]")
    init.add_argument("--force", action="store_true", help="replace an existing board")

    rung = commands.add_parser("rung", help="atomically add or update a rung")
    rung.add_argument("--dir", default=".")
    rung.add_argument("--track", required=True)
    rung.add_argument("--id", required=True, dest="rung_id")
    rung.add_argument("--value", required=True, type=float)
    rung.add_argument("--status", required=True, choices=sorted(STATUSES))
    rung.add_argument("--unit")
    rung.add_argument("--commit")
    rung.add_argument("--summary")
    rung.add_argument("--gate", "--parity", dest="gate")
    rung.add_argument("--duration-s", type=float)
    rung.add_argument("--metric", action="append", default=[], type=metric_pair, metavar="KEY=VAL")

    server = commands.add_parser("serve", help="serve the live dashboard")
    server.add_argument("--dir", default=".")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=18999)

    status = commands.add_parser("status", help="print a terminal scoreboard")
    status.add_argument("--dir", default=".")
    status.add_argument("--json", action="store_true")

    validate = commands.add_parser("validate", help="strictly validate a board")
    validate.add_argument("--dir", default=".")

    demo = commands.add_parser("demo", help="generate a realistic public demo")
    demo.add_argument("--dir", required=True)
    demo.add_argument("--serve", action="store_true")
    demo.add_argument("--host", default="0.0.0.0")
    demo.add_argument("--port", type=int, default=18999)
    return root


def format_number(value: float | None) -> str:
    return "—" if value is None else f"{value:,.3f}".rstrip("0").rstrip(".")


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def print_status(board: dict[str, Any]) -> None:
    print(f"\n{board['title']}\n{board['subtitle']}\n")
    for track_id, track in board["tracks"].items():
        best, winner = champion(track)
        rungs = track["rungs"]
        counts = {name: sum(r["status"] == name for r in rungs) for name in STATUSES}
        print(f"{track_id} · {track['label']}  [{track['direction']} is better]")
        print(f"  champion : {format_number(best)} {track['unit']}  ({winner['id'] if winner else 'metadata baseline'})")
        print(f"  baseline : {format_number(track['baseline'])} {track['unit']}   target: {format_number(track['target'])} {track['unit']}")
        print(f"  explored : {len(rungs)}   kept: {counts['kept']}   rejected: {counts['rejected']}   testing: {counts['testing']}")
        active = [r for r in rungs if r["status"] == "testing"]
        for rung in active:
            started = parse_time(rung["started_at"])
            from datetime import datetime, timezone
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() if started else 0
            print(f"  LIVE     : {rung['id']} · {format_duration(elapsed)} · {rung['summary']}")
        print()


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            board = initialize(args.dir, args.title, args.subtitle, args.track, force=args.force)
            print(f"Initialized {len(board['tracks'])} track(s) in {Path(args.dir).resolve()}")
        elif args.command == "rung":
            rung = upsert_rung(args.dir, track=args.track, rung_id=args.rung_id,
                               value=args.value, status=args.status, unit=args.unit,
                               commit=args.commit, summary=args.summary, gate=args.gate,
                               duration_s=args.duration_s, metrics=dict(args.metric))
            duration = f" · {format_duration(rung.get('duration_s'))}" if args.status != "testing" else ""
            print(f"{args.track}/{args.rung_id}: {args.status} · {format_number(args.value)} {rung['unit']}{duration}")
        elif args.command == "serve":
            board = load_board(args.dir)
            print(f"{board['title']} · {board['subtitle']}")
            serve(args.dir, args.host, args.port)
        elif args.command == "status":
            board = load_board(args.dir)
            print(json.dumps(board, indent=2) if args.json else "", end="\n" if args.json else "")
            if not args.json:
                print_status(board)
        elif args.command == "validate":
            board = load_board(args.dir)
            total = sum(len(t["rungs"]) for t in board["tracks"].values())
            print(f"Valid: {len(board['tracks'])} track(s), {total} rung(s)")
        elif args.command == "demo":
            board = make_demo(args.dir)
            print(f"Demo ready: {len(board['tracks'])} tracks in {Path(args.dir).resolve()}")
            if args.serve:
                serve(args.dir, args.host, args.port)
        return 0
    except (ValidationError, OSError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            print("\nStopped.", file=sys.stderr)
        else:
            print(f"ladder: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

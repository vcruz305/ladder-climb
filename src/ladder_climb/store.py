"""Locked read-modify-write operations; ladder.json is never edited in place."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .schema import ID_RE, ValidationError, parse_time, utc_now, validate_board


@contextmanager
def board_lock(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "ladder.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write(path: Path, payload: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def save_board(directory: Path, board: dict[str, Any]) -> None:
    validate_board(board)
    payload = json.dumps(board, indent=2, ensure_ascii=False) + "\n"
    atomic_write(directory / "ladder.json", payload)


def initialize(
    directory: str | Path,
    title: str,
    subtitle: str,
    tracks: list[dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "ladder.json"
    if path.exists() and not force:
        raise ValidationError(f"{path} already exists; use --force to replace it")
    if not tracks:
        raise ValidationError("at least one --track is required")
    definitions: dict[str, Any] = {}
    for spec in tracks:
        track_id = spec["id"]
        if not ID_RE.fullmatch(track_id) or track_id in definitions:
            raise ValidationError(f"invalid or duplicate track id: {track_id!r}")
        definitions[track_id] = {
            "label": spec["label"],
            "unit": spec["unit"],
            "baseline": spec.get("baseline"),
            "target": spec.get("target"),
            "direction": spec.get("direction", "higher"),
            "rungs": [],
        }
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    board = {
        "schema_version": 1,
        "title": title,
        "subtitle": subtitle,
        "created_at": now,
        "updated_at": now,
        "tracks": definitions,
    }
    with board_lock(root):
        save_board(root, board)
    return board


def upsert_rung(
    directory: str | Path,
    *,
    track: str,
    rung_id: str,
    value: float,
    status: str,
    unit: str | None = None,
    commit: str | None = None,
    summary: str | None = None,
    gate: str | None = None,
    duration_s: float | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(directory).expanduser().resolve()
    if not ID_RE.fullmatch(rung_id):
        raise ValidationError("rung id must match [A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
    if duration_s is not None and duration_s < 0:
        raise ValidationError("duration cannot be negative")
    with board_lock(root):
        path = root / "ladder.json"
        try:
            with path.open(encoding="utf-8") as handle:
                board = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ValidationError(f"cannot read {path}: {exc}") from exc
        validate_board(board)
        if track not in board["tracks"]:
            raise ValidationError(f"unknown track {track!r}")
        definition = board["tracks"][track]
        if unit is not None and unit != definition["unit"]:
            raise ValidationError(f"unit must be {definition['unit']!r} for this track")
        rungs = definition["rungs"]
        existing = next((r for r in rungs if r["id"] == rung_id), None)
        rung = dict(existing or {})
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        rung.update({
            "id": rung_id,
            "status": status,
            "value": value,
            "unit": unit or definition["unit"],
            "summary": summary if summary is not None else rung.get("summary", ""),
            "commit": commit if commit is not None else rung.get("commit"),
            "gate": gate if gate is not None else rung.get("gate"),
            "metrics": {**rung.get("metrics", {}), **(metrics or {})},
            "updated_at": now,
        })
        if status == "testing":
            if not existing or existing.get("status") != "testing" or not existing.get("started_at"):
                rung["started_at"] = now
            rung["duration_s"] = None
        else:
            if duration_s is not None:
                rung["duration_s"] = round(duration_s, 3)
            elif rung.get("started_at"):
                started = parse_time(rung["started_at"])
                rung["duration_s"] = round(max(0.0, (now_dt - started).total_seconds()), 3) if started else None
            else:
                rung["duration_s"] = None
        if existing:
            rungs[rungs.index(existing)] = rung
        else:
            rungs.append(rung)
        board["updated_at"] = now
        save_board(root, board)
        return rung

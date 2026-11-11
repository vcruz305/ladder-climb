"""Board schema, validation, and champion calculations."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

STATUSES = {"testing", "kept", "rejected", "baseline"}
DIRECTIONS = {"higher", "lower"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


class ValidationError(ValueError):
    """Raised when a board or update violates the public schema."""


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.astimezone()
    except ValueError:
        return None


def number(value: Any, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError(f"{field} must be a finite number")
    return result


def better(direction: str, candidate: float, incumbent: float) -> bool:
    return candidate > incumbent if direction == "higher" else candidate < incumbent


def champion(track: dict[str, Any]) -> tuple[float | None, dict[str, Any] | None]:
    """Return the best value and rung; the metadata baseline has no rung."""
    direction = track["direction"]
    best = track.get("baseline")
    winner = None
    for rung in track.get("rungs", []):
        if rung["status"] != "kept":
            continue
        value = float(rung["value"])
        if best is None or better(direction, value, float(best)):
            best, winner = value, rung
    return best, winner


def load_board(directory: str | Path) -> dict[str, Any]:
    path = Path(directory).expanduser().resolve() / "ladder.json"
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ValidationError(f"No ladder.json in {path.parent}; run 'ladder init' first") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid ladder.json: {exc}") from exc
    validate_board(data)
    return data


def validate_board(data: Any) -> None:
    """Validate schema plus chronological champion monotonicity."""
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValidationError("schema_version must be 1")
    for key in ("title", "subtitle", "created_at", "updated_at"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValidationError(f"{key} must be a non-empty string")
    tracks = data.get("tracks")
    if not isinstance(tracks, dict) or not tracks:
        raise ValidationError("tracks must be a non-empty object")
    for track_id, track in tracks.items():
        _validate_track(track_id, track)


def _validate_track(track_id: str, track: Any) -> None:
    prefix = f"track {track_id!r}"
    if not ID_RE.fullmatch(track_id) or not isinstance(track, dict):
        raise ValidationError(f"{prefix}: invalid id or definition")
    for key in ("label", "unit", "direction"):
        if not isinstance(track.get(key), str) or not track[key]:
            raise ValidationError(f"{prefix}: {key} must be a non-empty string")
    if track["direction"] not in DIRECTIONS:
        raise ValidationError(f"{prefix}: direction must be higher or lower")
    number(track.get("baseline"), f"{prefix}.baseline", optional=True)
    number(track.get("target"), f"{prefix}.target", optional=True)
    rungs = track.get("rungs")
    if not isinstance(rungs, list):
        raise ValidationError(f"{prefix}: rungs must be an array")
    seen: set[str] = set()
    best = track.get("baseline")
    for index, rung in enumerate(rungs):
        where = f"{prefix}.rungs[{index}]"
        if not isinstance(rung, dict) or not ID_RE.fullmatch(str(rung.get("id", ""))):
            raise ValidationError(f"{where}: invalid rung or id")
        if rung["id"] in seen:
            raise ValidationError(f"{where}: duplicate rung id")
        seen.add(rung["id"])
        if rung.get("status") not in STATUSES:
            raise ValidationError(f"{where}: invalid status")
        value = number(rung.get("value"), f"{where}.value")
        if rung.get("unit") != track["unit"]:
            raise ValidationError(f"{where}: unit must match its track")
        for key in ("summary", "commit", "gate", "started_at", "updated_at"):
            if key in rung and rung[key] is not None and not isinstance(rung[key], str):
                raise ValidationError(f"{where}.{key} must be a string or null")
        duration = rung.get("duration_s")
        if duration is not None and number(duration, f"{where}.duration_s") < 0:
            raise ValidationError(f"{where}.duration_s cannot be negative")
        if rung["status"] == "testing" and parse_time(rung.get("started_at")) is None:
            raise ValidationError(f"{where}: testing requires a valid started_at")
        metrics = rung.get("metrics", {})
        if not isinstance(metrics, dict) or not all(isinstance(k, str) for k in metrics):
            raise ValidationError(f"{where}.metrics must be an object with string keys")
        if rung["status"] == "kept":
            if rung.get("gate") not in (None, "", "pass", "passed"):
                raise ValidationError(f"{where}: kept rungs require a passing gate")
            if best is not None and better(track["direction"], float(best), float(value)):
                raise ValidationError(f"{where}: kept rung regresses the champion")
            if best is None or better(track["direction"], float(value), float(best)):
                best = float(value)

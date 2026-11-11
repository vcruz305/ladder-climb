"""Schema v2, tolerant v1 loading, validation, and champion math."""
from __future__ import annotations
import json, math, re
from datetime import datetime
from pathlib import Path
from typing import Any
STATUSES = {"testing", "kept", "rejected", "baseline", "interrupted"}
TERMINAL = {"kept", "rejected", "interrupted", "baseline"}
REVIEWS = {"pending", "verified", "flagged"}
DIRECTIONS = {"higher", "lower"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
class ValidationError(ValueError): pass
def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds").replace("+00:00", "Z")
def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value: return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError: return None
def number(value: Any, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional: return None
    if isinstance(value, bool) or not isinstance(value, (int, float)): raise ValidationError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result): raise ValidationError(f"{field} must be a finite number")
    return result
def better(direction: str, candidate: float, incumbent: float) -> bool:
    return candidate > incumbent if direction == "higher" else candidate < incumbent
def champion(track: dict[str, Any]) -> tuple[float | None, dict[str, Any] | None]:
    best, winner = track.get("baseline"), None
    for rung in track.get("rungs", []):
        if rung.get("status") != "kept" or rung.get("value") is None: continue
        value = float(rung["value"])
        if best is None or better(track["direction"], value, float(best)): best, winner = value, rung
    return best, winner
def _rung_v2(raw: dict[str, Any], unit: str, legacy: bool) -> dict[str, Any]:
    rung = dict(raw)
    if "id" not in rung and "rung" in rung: rung["id"] = rung.pop("rung")
    if "value" not in rung: rung["value"] = rung.pop("metric_tps", rung.pop("value_tps", None))
    if "summary" not in rung: rung["summary"] = rung.pop("notes", rung.pop("title", "")) or ""
    rung.setdefault("unit", unit); rung.setdefault("review", "pending"); rung.setdefault("gate", None)
    if legacy: rung.setdefault("duration_s", None)
    return rung
def normalize_board(raw: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    legacy = raw.get("schema_version") != 2; board = dict(raw)
    stamp = raw.get("updated_at") or raw.get("created_at") or utc_now()
    board.update({"schema_version": 2, "title": raw.get("title") or raw.get("model_name") or raw.get("model") or model or "Ladder Climb",
        "subtitle": raw.get("subtitle") or ("Legacy board" if legacy else "Live optimization campaign"),
        "created_at": raw.get("created_at") or stamp, "updated_at": stamp,
        "model": raw.get("model") or model or raw.get("title") or "legacy",
        "model_name": raw.get("model_name") or raw.get("model") or raw.get("title") or "Legacy model",
        "campaign_id": raw.get("campaign_id") or "legacy", "revision": int(raw.get("revision", 0) or 0)})
    tracks = {}
    for track_id, original in raw.get("tracks", {}).items():
        track = dict(original); unit = track.get("unit") or ("tok/s" if "baseline_tps" in track else "value")
        track.update({"label": track.get("label") or track_id, "unit": unit,
            "baseline": track.get("baseline", track.get("baseline_tps")), "target": track.get("target"),
            "direction": track.get("direction") or "higher", "rungs": [_rung_v2(r, unit, legacy) for r in track.get("rungs", [])]})
        tracks[track_id] = track
    board["tracks"] = tracks; return board
def load_board(directory: str | Path) -> dict[str, Any]:
    path = Path(directory).expanduser().resolve() / "ladder.json"
    try:
        with path.open(encoding="utf-8") as handle: raw = json.load(handle)
    except FileNotFoundError as exc: raise ValidationError(f"No ladder.json in {path.parent}; run 'ladder init' first") from exc
    except json.JSONDecodeError as exc: raise ValidationError(f"Invalid ladder.json: {exc}") from exc
    if not isinstance(raw, dict): raise ValidationError("board must be an object")
    legacy = raw.get("schema_version") != 2; board = normalize_board(raw); validate_board(board, legacy=legacy); return board
def validate_board(data: Any, *, legacy: bool = False) -> None:
    if not isinstance(data, dict) or data.get("schema_version") not in (1, 2): raise ValidationError("schema_version must be 1 or 2")
    if data["schema_version"] == 1: data = normalize_board(data); legacy = True
    for key in ("title", "subtitle", "created_at", "updated_at"):
        if not isinstance(data.get(key), str) or not data[key]: raise ValidationError(f"{key} must be a non-empty string")
    if not legacy:
        if not ID_RE.fullmatch(str(data.get("campaign_id", ""))): raise ValidationError("invalid campaign_id")
        if not isinstance(data.get("revision"), int) or data["revision"] < 0: raise ValidationError("revision must be a non-negative integer")
        for key in ("created_at", "updated_at"):
            if parse_time(data[key]) is None: raise ValidationError(f"{key} must be timezone-aware ISO time")
    tracks = data.get("tracks")
    if not isinstance(tracks, dict) or not tracks: raise ValidationError("tracks must be a non-empty object")
    for track_id, track in tracks.items(): _validate_track(track_id, track, legacy)
def _validate_track(track_id: str, track: Any, legacy: bool) -> None:
    prefix = f"track {track_id!r}"
    if not ID_RE.fullmatch(track_id) or not isinstance(track, dict): raise ValidationError(f"{prefix}: invalid id or definition")
    for key in ("label", "unit", "direction"):
        if not isinstance(track.get(key), str) or not track[key]: raise ValidationError(f"{prefix}: {key} must be a non-empty string")
    if track["direction"] not in DIRECTIONS: raise ValidationError(f"{prefix}: direction must be higher or lower")
    number(track.get("baseline"), f"{prefix}.baseline", optional=True); number(track.get("target"), f"{prefix}.target", optional=True)
    rungs = track.get("rungs")
    if not isinstance(rungs, list): raise ValidationError(f"{prefix}: rungs must be an array")
    seen, best = set(), track.get("baseline")
    for index, rung in enumerate(rungs):
        where = f"{prefix}.rungs[{index}]"
        if not isinstance(rung, dict) or not ID_RE.fullmatch(str(rung.get("id", ""))): raise ValidationError(f"{where}: invalid rung or id")
        if rung["id"] in seen: raise ValidationError(f"{where}: duplicate rung id")
        seen.add(rung["id"])
        if rung.get("status") not in STATUSES: raise ValidationError(f"{where}: invalid status")
        value = number(rung.get("value"), f"{where}.value", optional=rung.get("status") == "interrupted")
        if rung.get("unit") != track["unit"]: raise ValidationError(f"{where}: unit must match its track")
        for key in ("summary", "commit", "gate", "started_at", "updated_at", "ended_at", "wave", "session", "session_id", "agent", "reviewer", "review_notes", "reviewed_at"):
            if key in rung and rung[key] is not None and not isinstance(rung[key], str): raise ValidationError(f"{where}.{key} must be a string or null")
        if rung.get("review", "pending") not in REVIEWS: raise ValidationError(f"{where}: invalid review")
        duration = rung.get("duration_s")
        if duration is not None and number(duration, f"{where}.duration_s") < 0: raise ValidationError(f"{where}.duration_s cannot be negative")
        if rung["status"] == "testing" and parse_time(rung.get("started_at")) is None: raise ValidationError(f"{where}: testing requires a valid started_at")
        if not legacy:
            for key in ("updated_at", "started_at", "ended_at"):
                if rung.get(key) is not None and parse_time(rung[key]) is None: raise ValidationError(f"{where}.{key} must be timezone-aware ISO time")
            start, updated = parse_time(rung.get("started_at")), parse_time(rung.get("updated_at"))
            if start and updated and updated < start and not rung.get("clock_skew"): raise ValidationError(f"{where}: updated_at precedes started_at")
        metrics = rung.get("metrics", {})
        if not isinstance(metrics, dict) or not all(isinstance(k, str) for k in metrics): raise ValidationError(f"{where}.metrics must be an object with string keys")
        if rung["status"] == "kept":
            if rung.get("gate") not in (None, "", "pass", "passed") and not str(rung.get("gate")).upper().endswith("PASS"): raise ValidationError(f"{where}: kept rungs require a passing gate")
            if not legacy and best is not None and value is not None and better(track["direction"], float(best), float(value)): raise ValidationError(f"{where}: kept rung regresses the champion")
            if best is None or (value is not None and better(track["direction"], float(value), float(best))): best = float(value)

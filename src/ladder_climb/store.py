"""Per-board locking, atomic writes, workspaces, reviews, and immutable archives."""
from __future__ import annotations
import fcntl, json, os, tempfile, time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from .schema import ID_RE, TERMINAL, REVIEWS, ValidationError, champion, load_board, normalize_board, parse_time, utc_now, validate_board

@dataclass(frozen=True)
class BoardPaths:
    feed: Path
    lock: Path
    model_dir: Path

def _id(value: str | None, kind: str) -> str | None:
    if value is not None and not ID_RE.fullmatch(value): raise ValidationError(f"invalid {kind} id")
    return value

def resolve_board_dir(directory: str | Path, model: str | None = None, campaign: str | None = None) -> Path:
    root = Path(directory).expanduser().resolve(); _id(model, "model"); _id(campaign, "campaign")
    if model is None and campaign is None and not (root / "workspace.json").is_file(): return root
    if campaign and not model: raise ValidationError("--campaign requires --model")
    if not model:
        manifest = root / "workspace.json"
        if manifest.is_file():
            try: model = json.loads(manifest.read_text(encoding="utf-8")).get("default_model")
            except json.JSONDecodeError as exc: raise ValidationError(f"invalid workspace.json: {exc}") from exc
        if not model: raise ValidationError("workspace requires --model")
    base = root / "models" / model
    return base / "campaigns" / campaign if campaign else base

def paths_for(directory: str | Path, model: str | None = None, campaign: str | None = None) -> BoardPaths:
    root = resolve_board_dir(directory, model, campaign)
    model_dir = root.parents[1] if campaign else root
    return BoardPaths(root / "ladder.json", root / "ladder.lock", model_dir)

@contextmanager
def board_lock(directory: Path | BoardPaths, timeout: float = 10.0) -> Iterator[None]:
    lock = directory.lock if isinstance(directory, BoardPaths) else directory / "ladder.lock"
    lock.parent.mkdir(parents=True, exist_ok=True); deadline = time.monotonic() + timeout
    with lock.open("a+") as handle:
        while True:
            try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.monotonic() >= deadline: raise TimeoutError(f"timed out after {timeout:g}s waiting for {lock}")
                time.sleep(0.02)
        try: yield
        finally: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise

def save_board(directory: Path | BoardPaths, board: dict[str, Any]) -> None:
    target = directory.feed if isinstance(directory, BoardPaths) else directory / "ladder.json"
    validate_board(board); atomic_write(target, json.dumps(board, indent=2, ensure_ascii=False) + "\n")

def _definitions(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    if not tracks: raise ValidationError("at least one --track is required")
    result = {}
    for spec in tracks:
        track_id = spec["id"]
        if not ID_RE.fullmatch(track_id) or track_id in result: raise ValidationError(f"invalid or duplicate track id: {track_id!r}")
        result[track_id] = {"label": spec["label"], "unit": spec["unit"], "baseline": spec.get("baseline"),
            "target": spec.get("target"), "direction": spec.get("direction", "higher"), "rungs": []}
    return result

def initialize(directory: str | Path, title: str, subtitle: str, tracks: list[dict[str, Any]], *, force: bool = False,
               model: str | None = None, model_name: str | None = None, hardware: str | None = None,
               campaign_id: str | None = None, lock_timeout: float = 10.0) -> dict[str, Any]:
    root = Path(directory).expanduser().resolve(); root.mkdir(parents=True, exist_ok=True)
    paths = paths_for(root, model); definitions = _definitions(tracks); now = utc_now()
    board = {"schema_version": 2 if model else 1, "title": title, "subtitle": subtitle, "created_at": now,
             "updated_at": now, "tracks": definitions}
    if model: board.update(model=model, model_name=model_name or model, hardware=hardware or "", campaign_id=campaign_id or "active", revision=0)
    with board_lock(paths, lock_timeout):
        if paths.feed.exists() and not force: raise ValidationError(f"{paths.feed} already exists; use --force to replace it")
        save_board(paths, board)
    if model:
        manifest_path = root / "workspace.json"
        with board_lock(root / "workspace", lock_timeout):
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version": 2, "models": {}, "default_model": model}
            manifest.setdefault("models", {})[model] = {"id": model, "model_name": model_name or model, "hardware": hardware or "", "active_campaign": board["campaign_id"]}
            manifest.setdefault("default_model", model)
            atomic_write(manifest_path, json.dumps(manifest, indent=2) + "\n")
    return board

def _check_revision(board: dict[str, Any], expected: int | None) -> None:
    if expected is not None and board.get("revision", 0) != expected: raise ValidationError(f"revision conflict: expected {expected}, current {board.get('revision', 0)}")

def upsert_rung(directory: str | Path, *, track: str, rung_id: str, value: float | None, status: str,
                unit: str | None = None, commit: str | None = None, summary: str | None = None, gate: str | None = None,
                duration_s: float | None = None, metrics: dict[str, Any] | None = None, model: str | None = None,
                campaign: str | None = None, wave: str | None = None, session: str | None = None, agent: str | None = None,
                expected_revision: int | None = None, force_update: bool = False, lock_timeout: float = 10.0) -> dict[str, Any]:
    if not ID_RE.fullmatch(rung_id): raise ValidationError("invalid rung id")
    if duration_s is not None and duration_s < 0: raise ValidationError("duration cannot be negative")
    if campaign: raise ValidationError("archived campaigns are immutable")
    paths = paths_for(directory, model, campaign)
    with board_lock(paths, lock_timeout):
        board = load_board(paths.feed.parent); _check_revision(board, expected_revision)
        if track not in board["tracks"]: raise ValidationError(f"unknown track {track!r}")
        definition = board["tracks"][track]
        if unit is not None and unit != definition["unit"]: raise ValidationError(f"unit must be {definition['unit']!r}")
        rungs = definition["rungs"]; existing = next((r for r in rungs if r["id"] == rung_id), None)
        if existing and existing.get("status") == "testing" and status == "testing" and expected_revision is None and not force_update:
            raise ValidationError("duplicate testing rung; use --expected-revision for an explicit update")
        if existing and existing.get("status") in TERMINAL and expected_revision is None and not force_update:
            raise ValidationError("terminal rung is protected; use --expected-revision for metadata or --force-update")
        rung = dict(existing or {}); now_dt = datetime.now(timezone.utc); now = utc_now(); previous = rung.get("status")
        chosen = value if value is not None else rung.get("value", 0 if status != "interrupted" else None)
        rung.update({"id": rung_id, "status": status, "value": chosen, "unit": unit or definition["unit"],
            "summary": summary if summary is not None else rung.get("summary", ""), "commit": commit if commit is not None else rung.get("commit"),
            "gate": gate if gate is not None else rung.get("gate"), "metrics": {**rung.get("metrics", {}), **(metrics or {})}, "updated_at": now})
        for key, item in (("wave", wave), ("session", session), ("agent", agent)):
            if item is not None: rung[key] = item
        rung.setdefault("review", "pending")
        if status == "testing":
            if not existing or previous != "testing" or not rung.get("started_at"): rung["started_at"] = now
            rung["duration_s"] = None; rung.pop("ended_at", None)
        elif previous in TERMINAL:
            pass  # terminal timing is immutable, including externally supplied durations
        else:
            rung["ended_at"] = now
            if duration_s is not None: rung["duration_s"] = round(duration_s, 3)
            elif rung.get("started_at"):
                started = parse_time(rung["started_at"]); elapsed = (now_dt - started).total_seconds() if started else None
                if elapsed is not None and elapsed < 0:
                    rung["duration_s"] = None; rung["clock_skew"] = round(elapsed, 3); rung["review"] = "flagged"
                else: rung["duration_s"] = round(elapsed, 3) if elapsed is not None else None
            else: rung["duration_s"] = round(duration_s, 3) if duration_s is not None else None
        if existing: rungs[rungs.index(existing)] = rung
        else: rungs.append(rung)
        board["updated_at"] = now; board["revision"] = board.get("revision", 0) + 1
        save_board(paths, board); rung["revision"] = board["revision"]; return rung

def claim_rung(directory: str | Path, *, track: str, prefix: str, model: str | None = None, lock_timeout: float = 10.0,
               agent: str | None = None, wave: str | None = None, session: str | None = None) -> dict[str, Any]:
    if not prefix or not ID_RE.fullmatch(prefix + "-1"): raise ValidationError("invalid rung prefix")
    paths = paths_for(directory, model)
    with board_lock(paths, lock_timeout):
        board = load_board(paths.feed.parent)
        if track not in board["tracks"]: raise ValidationError(f"unknown track {track!r}")
        used = {r["id"] for t in board["tracks"].values() for r in t["rungs"]}; number = 1
        while f"{prefix}-{number:03d}" in used: number += 1
        rung_id = f"{prefix}-{number:03d}"
    try:
        return upsert_rung(directory, track=track, rung_id=rung_id, value=0, status="testing", gate="pending", model=model,
                           agent=agent, wave=wave, session=session, expected_revision=board.get("revision", 0), lock_timeout=lock_timeout)
    except ValidationError as exc:
        if "revision conflict" not in str(exc): raise
        return claim_rung(directory, track=track, prefix=prefix, model=model, lock_timeout=lock_timeout, agent=agent, wave=wave, session=session)

def review_rung(directory: str | Path, *, track: str, rung_id: str, review: str, reviewer: str | None = None,
                notes: str | None = None, model: str | None = None, expected_revision: int | None = None, lock_timeout: float = 10.0) -> dict[str, Any]:
    if review not in REVIEWS: raise ValidationError("invalid review")
    paths = paths_for(directory, model)
    with board_lock(paths, lock_timeout):
        board = load_board(paths.feed.parent); _check_revision(board, expected_revision)
        rung = next((r for r in board["tracks"].get(track, {}).get("rungs", []) if r["id"] == rung_id), None)
        if rung is None: raise ValidationError("unknown track/rung")
        rung.update(review=review, reviewer=reviewer, review_notes=notes or "", reviewed_at=utc_now(), updated_at=utc_now())
        board["updated_at"] = utc_now(); board["revision"] = board.get("revision", 0) + 1; save_board(paths, board)
        return dict(rung, revision=board["revision"])

def archive_campaign(directory: str | Path, *, model: str, campaign: str, title: str | None = None,
                     start_next: bool = False, lock_timeout: float = 10.0) -> dict[str, Any]:
    _id(campaign, "campaign"); source = paths_for(directory, model); target = paths_for(directory, model, campaign)
    with board_lock(source, lock_timeout):
        if target.feed.exists() or (target.feed.parent / "manifest.json").exists(): raise ValidationError("archive already exists and is immutable")
        board = load_board(source.feed.parent); parent_campaign = board.get("campaign_id", "active"); board = dict(board, campaign_id=campaign, title=title or board["title"])
        save_board(target, board)
        counts = {s: sum(r["status"] == s for t in board["tracks"].values() for r in t["rungs"]) for s in TERMINAL | {"testing"}}
        reviews = {s: sum(r.get("review", "pending") == s for t in board["tracks"].values() for r in t["rungs"]) for s in REVIEWS}
        champions = {k: {"value": champion(t)[0], "rung_id": (champion(t)[1] or {}).get("id"), "unit": t["unit"]} for k, t in board["tracks"].items()}
        manifest = {"schema_version": 2, "campaign_id": campaign, "title": board["title"], "model": model,
            "model_name": board.get("model_name"), "hardware": board.get("hardware"), "started_at": board["created_at"],
            "ended_at": utc_now(), "rungs": counts, "reviews": reviews, "champions": champions, "parent_campaign": parent_campaign}
        atomic_write(target.feed.parent / "manifest.json", json.dumps(manifest, indent=2) + "\n")
        if start_next:
            active = load_board(source.feed.parent)
            for spec in active["tracks"].values(): spec["rungs"] = []
            active.update(campaign_id=campaign + "-next", created_at=utc_now(), updated_at=utc_now(), revision=active.get("revision", 0) + 1)
            save_board(source, active)
        workspace_path = source.model_dir.parent.parent / "workspace.json"
        if workspace_path.is_file():
            workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
            if model in workspace.get("models", {}):
                workspace["models"][model]["active_campaign"] = (campaign + "-next") if start_next else parent_campaign
                atomic_write(workspace_path, json.dumps(workspace, indent=2) + "\n")
        return manifest

def list_models(directory: str | Path) -> list[dict[str, Any]]:
    root = Path(directory).expanduser().resolve()
    if (root / "ladder.json").is_file(): return [{"id": "legacy", "model_name": load_board(root)["model_name"], "active_campaign": "legacy"}]
    manifest = json.loads((root / "workspace.json").read_text()) if (root / "workspace.json").exists() else {"models": {}}
    return sorted(manifest.get("models", {}).values(), key=lambda m: m["id"])

def list_campaigns(directory: str | Path, model: str) -> list[dict[str, Any]]:
    base = resolve_board_dir(directory, model); result = [{"campaign_id": load_board(base).get("campaign_id", "active"), "active": True}]
    folder = base / "campaigns"
    for item in sorted(folder.glob("*/manifest.json")) if folder.is_dir() else []:
        try: result.append(dict(json.loads(item.read_text()), active=False))
        except (OSError, json.JSONDecodeError): continue
    return result

"""Cross-model history, prior-champion deltas, filtering, and safe exports."""
from __future__ import annotations
import csv, io, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .schema import better, load_board, parse_time, utc_now
from .store import list_models, paths_for

def _cursor(row: dict[str, Any]) -> str:
    return "|".join(str(row.get(k) or "") for k in ("updated_at", "model", "campaign", "track", "rung"))

COLUMNS = ["model", "model_name", "campaign", "track", "rung", "summary", "value", "unit", "prior_id",
           "prior_value", "delta_abs", "delta_pct", "status", "gate", "review", "reviewer", "review_notes",
           "wave", "session", "agent", "commit", "started_at", "ended_at", "updated_at", "duration_s", "metrics"]

def _stamp(row: dict[str, Any]) -> float:
    parsed = parse_time(row.get("updated_at") or row.get("started_at"))
    return parsed.timestamp() if parsed else 0.0

def collect_history(directory: str | Path, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}; root = Path(directory).expanduser().resolve(); rows = []
    for model in list_models(root):
        model_id = model["id"] if model["id"] != "legacy" else None
        board = load_board(paths_for(root, model_id).feed.parent)
        rows.extend(_board_rows(board, model["id"], board.get("campaign_id", "legacy")))
        if model_id:
            folder = paths_for(root, model_id).feed.parent / "campaigns"
            for feed in sorted(folder.glob("*/ladder.json")) if folder.is_dir() else []:
                archived = load_board(feed.parent)
                rows.extend(_board_rows(archived, model["id"], feed.parent.name))
    return filter_history(rows, filters)

def _board_rows(board: dict[str, Any], model: str, campaign: str) -> list[dict[str, Any]]:
    result = []
    for track_id, track in board["tracks"].items():
        ordered = sorted(track["rungs"], key=_stamp); best = track.get("baseline"); prior_id = None
        for rung in ordered:
            value = rung.get("value"); prior_value = best; delta_abs = delta_pct = None
            if rung.get("status") == "kept" and value is not None:
                if best is not None:
                    delta_abs = value - best
                    if best != 0: delta_pct = delta_abs / abs(best) * 100
            row = {"model": model, "model_name": board.get("model_name", model), "campaign": campaign,
                "track": track_id, "rung": rung["id"], "unit": track["unit"], "prior_id": prior_id,
                "prior_value": prior_value, "delta_abs": delta_abs, "delta_pct": delta_pct}
            if rung.get("status") == "kept" and value is not None and (best is None or better(track["direction"], value, best)):
                best, prior_id = value, rung["id"]
            row.update({k: rung.get(k) for k in COLUMNS if k not in row}); row["value"] = value
            row["metrics"] = rung.get("metrics", {}); result.append(row)
    return result

def filter_history(rows: list[dict[str, Any]], f: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = {"id": "rung", "campaign_id": "campaign"}; f = {aliases.get(k, k): v for k, v in f.items() if v not in (None, "")}
    selected = []
    for row in rows:
        if any(k in {"model", "campaign", "track", "status", "gate", "review", "wave", "session"} and str(row.get(k) or "") != str(v) for k, v in f.items()): continue
        query = str(f.get("search", "")).lower()
        if query and query not in json.dumps(row, ensure_ascii=False).lower(): continue
        for key, op in (("since", lambda a, b: a >= b), ("until", lambda a, b: a <= b)):
            if key in f:
                left, right = parse_time(row.get("updated_at")), parse_time(f[key])
                if not left or not right or not op(left, right): break
        else: selected.append(row)
    chronological = str(f.get("sort", "newest")) == "chronological"
    return sorted(selected, key=lambda r: (_stamp(r), r["model"], r["campaign"], r["track"], r["rung"]), reverse=not chronological)

def history_payload(directory: str | Path, filters: dict[str, Any] | None = None, *, limit: int = 500, offset: int = 0, cursor: str | None = None) -> dict[str, Any]:
    rows = collect_history(directory, filters); limit = max(1, min(int(limit), 10000)); offset = max(0, int(offset))
    if cursor:
        match = next((i for i, r in enumerate(rows) if _cursor(r) == cursor), None)
        if match is None: raise ValueError("invalid or expired history cursor")
        offset = match + 1
    page = rows[offset:offset + limit]; has_more = offset + limit < len(rows)
    return {"schema_version": 2, "now": utc_now(), "total": len(rows), "offset": offset, "limit": limit,
            "next_offset": offset + limit if has_more else None, "next_cursor": _cursor(page[-1]) if has_more and page else None,
            "filters": filters or {}, "rows": page}

def neutralize(value: Any) -> Any:
    if isinstance(value, (dict, list)): value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None: return ""
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text

def export_history(directory: str | Path, fmt: str, filters: dict[str, Any] | None = None) -> tuple[str, str]:
    rows = collect_history(directory, filters); payload = {"total": len(rows), "rows": rows}; metadata = {"schema_version": 2, "exported_at": utc_now(), "filters": filters or {}}
    if fmt == "json": return json.dumps(dict(metadata, total=payload["total"], rows=payload["rows"]), indent=2) + "\n", "application/json; charset=utf-8"
    if fmt != "csv": raise ValueError("format must be json or csv")
    output = io.StringIO(); output.write("# " + json.dumps(metadata, separators=(",", ":")) + "\n")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, extrasaction="ignore"); writer.writeheader()
    for row in payload["rows"]: writer.writerow({key: neutralize(row.get(key)) for key in COLUMNS})
    return output.getvalue(), "text/csv; charset=utf-8"

"""Generate a synthetic three-model workspace with live and archived climbs."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .schema import load_board
from .store import archive_campaign, initialize, paths_for, review_rung, upsert_rung
DEMO_RUNGS = {
    "prefill": [("kept", 142.8, "Vectorized tile loads and aligned shared-memory staging", "a10c7e21", 74, 1024, .018),
        ("rejected", 139.1, "Increased tile width without occupancy tuning", "b21d8e32", 49, 1024, .021),
        ("kept", 181.6, "Balanced workgroups for long prompt batches", "c32e9f43", 92, 1024, .015),
        ("kept", 236.4, "Fused dequantization with the matrix-inner loop", "d43fa054", 121, 1024, .013),
        ("rejected", 218.7, "Persistent kernel exceeded the register budget", "e540b165", 67, 1024, .019),
        ("kept", 284.9, "Two-stage pipeline with asynchronous tile prefetch", "f651c276", 108, 1024, .011),
        ("testing", 302., "Tune pipeline depth across short and long prompts", "0762d387", None, 1024, None)],
    "decode": [("kept", 24.6, "Reduced draft synchronization overhead", "1a72b3c4", 42, .78, .006),
        ("kept", 31.8, "Batched verification with compact token metadata", "2b83c4d5", 58, .81, .005),
        ("rejected", 29.4, "Longer draft window reduced acceptance efficiency", "3c94d5e6", 45, .64, .006),
        ("kept", 39.2, "Reusable verification workspace removed allocations", "4da5e6f7", 71, .83, .004),
        ("rejected", 35.1, "Aggressive cache policy failed the output gate", "5eb6f708", 39, .82, .029),
        ("kept", 47.5, "Adaptive draft depth from rolling acceptance", "6fc70819", 84, .86, .004),
        ("testing", 49.1, "Overlap draft preparation with verification", "70d8192a", None, .85, None)],
    "latency": [("kept", 88.2, "Removed redundant host-to-device metadata copies", "8a1b2c3d", 36, 32, .004),
        ("rejected", 91.7, "Synchronous profiling distorted the request path", "9b2c3d4e", 28, 32, .005),
        ("kept", 74.5, "Prewarmed kernels before the measured request", "ac3d4e5f", 47, 32, .003),
        ("kept", 62.8, "Single-producer scheduling queue with bounded batches", "bd4e5f60", 55, 32, .003),
        ("rejected", 65.9, "Unbounded queue traded latency for throughput", "ce5f6071", 41, 128, .003),
        ("kept", 51.3, "Coalesced scheduler wakeups and response writes", "df607182", 64, 32, .002),
        ("testing", 49.8, "Adaptive response batching under light load", "e0718293", None, 32, None)]}
TRACKS = [
    {"id": "prefill", "label": "Prompt Prefill", "unit": "prefill tok/s", "baseline": 120., "target": 320., "direction": "higher"},
    {"id": "decode", "label": "Speculative Decode", "unit": "decode tok/s", "baseline": 18., "target": 55., "direction": "higher"},
    {"id": "latency", "label": "Request Latency", "unit": "ms p50", "baseline": 96., "target": 45., "direction": "lower"}]
def _populate(directory: Path, model: str, source: dict[str, list], wave: str = "wave-2") -> None:
    for track_id, rungs in source.items():
        for index, (status, value, summary, commit, duration, batch, error) in enumerate(rungs, 1):
            rung_id = f"{track_id[:2].upper()}-{index:02d}"
            common = dict(directory=directory, model=model, track=track_id, rung_id=rung_id, value=value,
                commit=commit, summary=summary, metrics={"batch_tokens": batch, "median_runs": 5}, wave=wave,
                session="demo-session", agent=f"worker-{index % 3 + 1}")
            if error is not None: common["metrics"]["relative_error"] = error
            upsert_rung(**common, status="testing", gate="pending")
            if status != "testing":
                gate = "fail" if status == "rejected" and "failed" in summary else "pass"
                upsert_rung(**common, status=status, gate=gate, duration_s=duration)
def make_demo(directory: str | Path) -> dict[str, Any]:
    root = Path(directory).expanduser().resolve()
    initialize(root, "Atlas Optimization Campaign", "Synthetic multi-agent ladder-climb · paired benchmarks · correctness gated",
        TRACKS, model="atlas", model_name="Atlas 27B", hardware="Synthetic workstation", force=True)
    _populate(root, "atlas", DEMO_RUNGS)
    review_rung(root, model="atlas", track="prefill", rung_id="PR-06", review="verified", reviewer="demo-verifier", notes="All correctness fixtures pass")
    review_rung(root, model="atlas", track="decode", rung_id="DE-05", review="flagged", reviewer="demo-verifier", notes="Investigate output-gate failure")
    initialize(root, "Mosaic Optimization Campaign", "Second simultaneous synthetic ladder climb", TRACKS[:2],
        model="mosaic", model_name="Mosaic 16B", hardware="Synthetic workstation", force=True)
    smaller = {key: value[:5] for key, value in DEMO_RUNGS.items() if key in ("prefill", "decode")}
    _populate(root, "mosaic", smaller)
    initialize(root, "Archive Example", "Completed synthetic wave with independent review", TRACKS[:1],
        model="archivist", model_name="Archivist 8B", hardware="Synthetic archive", campaign_id="wave-2", force=True)
    _populate(root, "archivist", {"prefill": DEMO_RUNGS["prefill"][:4]}, "wave-1")
    review_rung(root, model="archivist", track="prefill", rung_id="PR-03", review="verified", reviewer="review-bot", notes="Archived evidence verified")
    archive_campaign(root, model="archivist", campaign="wave-1", title="Wave 1 · Foundation")
    return load_board(paths_for(root, "atlas").feed.parent)

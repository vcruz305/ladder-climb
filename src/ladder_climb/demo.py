"""Generate a deterministic-looking, entirely synthetic optimization campaign."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import load_board
from .store import initialize, upsert_rung

DEMO_RUNGS: dict[str, list[dict[str, Any]]] = {
    "prefill": [
        ("kept", 142.8, "Vectorized tile loads and aligned shared-memory staging", "a10c7e21", 74, 1024, 0.018),
        ("rejected", 139.1, "Increased tile width without occupancy tuning", "b21d8e32", 49, 1024, 0.021),
        ("kept", 181.6, "Balanced workgroups for long prompt batches", "c32e9f43", 92, 1024, 0.015),
        ("kept", 236.4, "Fused dequantization with the matrix-inner loop", "d43fa054", 121, 1024, 0.013),
        ("rejected", 218.7, "Persistent kernel exceeded the register budget", "e540b165", 67, 1024, 0.019),
        ("kept", 284.9, "Two-stage pipeline with asynchronous tile prefetch", "f651c276", 108, 1024, 0.011),
        ("testing", 302.0, "Tune pipeline depth across short and long prompts", "0762d387", None, 1024, None),
    ],
    "decode": [
        ("kept", 24.6, "Reduced draft synchronization overhead", "1a72b3c4", 42, 0.78, 0.006),
        ("kept", 31.8, "Batched verification with compact token metadata", "2b83c4d5", 58, 0.81, 0.005),
        ("rejected", 29.4, "Longer draft window reduced acceptance efficiency", "3c94d5e6", 45, 0.64, 0.006),
        ("kept", 39.2, "Reusable verification workspace removed allocations", "4da5e6f7", 71, 0.83, 0.004),
        ("rejected", 35.1, "Aggressive cache policy failed the output gate", "5eb6f708", 39, 0.82, 0.029),
        ("kept", 47.5, "Adaptive draft depth from rolling acceptance", "6fc70819", 84, 0.86, 0.004),
        ("testing", 49.1, "Overlap draft preparation with verification", "70d8192a", None, 0.85, None),
    ],
    "latency": [
        ("kept", 88.2, "Removed redundant host-to-device metadata copies", "8a1b2c3d", 36, 32, 0.004),
        ("rejected", 91.7, "Synchronous profiling distorted the request path", "9b2c3d4e", 28, 32, 0.005),
        ("kept", 74.5, "Prewarmed kernels before the measured request", "ac3d4e5f", 47, 32, 0.003),
        ("kept", 62.8, "Single-producer scheduling queue with bounded batches", "bd4e5f60", 55, 32, 0.003),
        ("rejected", 65.9, "Unbounded queue traded latency for throughput", "ce5f6071", 41, 128, 0.003),
        ("kept", 51.3, "Coalesced scheduler wakeups and response writes", "df607182", 64, 32, 0.002),
        ("testing", 49.8, "Adaptive response batching under light load", "e0718293", None, 32, None),
    ],
}


def make_demo(directory: str | Path) -> dict[str, Any]:
    tracks = [
        {"id": "prefill", "label": "Prompt Prefill", "unit": "prefill tok/s",
         "baseline": 120.0, "target": 320.0, "direction": "higher"},
        {"id": "decode", "label": "Speculative Decode", "unit": "decode tok/s",
         "baseline": 18.0, "target": 55.0, "direction": "higher"},
        {"id": "latency", "label": "Request Latency", "unit": "ms p50",
         "baseline": 96.0, "target": 45.0, "direction": "lower"},
    ]
    board = initialize(directory, "GPU Kernel Optimization Campaign",
                       "Synthetic multi-agent hill-climb · paired benchmarks · correctness gated",
                       tracks, force=True)
    for track_id, rungs in DEMO_RUNGS.items():
        for index, (status, value, summary, commit, duration, batch, error) in enumerate(rungs, 1):
            rung_id = f"{track_id[:2].upper()}-{index:02d}"
            common = dict(directory=directory, track=track_id, rung_id=rung_id,
                          value=value, commit=commit, summary=summary,
                          metrics={"batch_tokens": batch, "median_runs": 5})
            if error is not None:
                common["metrics"]["relative_error"] = error
            upsert_rung(**common, status="testing", gate="pending")
            if status != "testing":
                gate = "fail" if status == "rejected" and "failed" in summary else "pass"
                upsert_rung(**common, status=status, gate=gate, duration_s=duration)
    return load_board(directory)

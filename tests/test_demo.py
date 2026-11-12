from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ladder_climb.demo import make_demo
from ladder_climb.schema import champion, validate_board


class DemoTests(unittest.TestCase):
    def test_demo_is_valid_multitrack_and_multidirectional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = make_demo(directory)
            validate_board(board)
            self.assertEqual(len(board["tracks"]), 3)
            self.assertEqual({t["direction"] for t in board["tracks"].values()}, {"higher", "lower"})
            self.assertEqual(sum(len(t["rungs"]) for t in board["tracks"].values()), 21)
            self.assertEqual(sum(r["status"] == "testing" for t in board["tracks"].values() for r in t["rungs"]), 3)
            self.assertLess(champion(board["tracks"]["latency"])[0], board["tracks"]["latency"]["baseline"])
            self.assertGreater(champion(board["tracks"]["prefill"])[0], board["tracks"]["prefill"]["baseline"])
            from ladder_climb.store import list_campaigns, list_models
            self.assertEqual({m["id"] for m in list_models(directory)}, {"atlas", "mosaic", "archivist"})
            campaigns = list_campaigns(directory, "archivist")
            self.assertTrue(any(c["campaign_id"] == "wave-1" and not c["active"] for c in campaigns))
            self.assertEqual(board["tracks"]["prefill"]["rungs"][5]["review"], "verified")
            self.assertEqual(board["tracks"]["decode"]["rungs"][4]["review"], "flagged")

    def test_dashboard_has_no_campaign_specific_track_names(self) -> None:
        assets = Path(__file__).resolve().parents[1] / "src" / "ladder_climb" / "assets"
        html = (assets / "dashboard.html").read_text(encoding="utf-8")
        js = (assets / "dashboard.js").read_text(encoding="utf-8")
        charts = (assets / "charts.js").read_text(encoding="utf-8")
        self.assertIn('id="track-filters"', html)
        self.assertIn('class="model-dock"', html)
        self.assertIn('class="worker-strip"', html)
        self.assertIn("Object.entries(state.board.tracks", js)
        self.assertIn("track.direction", charts)
        self.assertIn("PDT = UTC−7", html)

    def test_model_dock_and_fleet_matrix_regressions(self) -> None:
        assets = Path(__file__).resolve().parents[1] / "src" / "ladder_climb" / "assets"
        html = (assets / "dashboard.html").read_text(encoding="utf-8")
        css = (assets / "dashboard.css").read_text(encoding="utf-8")
        js = (assets / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('<nav class="model-dock"', html)
        self.assertIn('id="model-tabs"', html)
        self.assertIn('id="overview"', html)
        self.assertIn(".model-tab{height:42px", css)
        self.assertIn("flex-direction:column", css)
        self.assertIn("model-tab-top", js)
        self.assertIn("model-telemetry", js)
        self.assertIn("model-beacon", js)
        self.assertIn("Fleet ('+models.length+')'", js)
        self.assertIn("m.champions", js)
        self.assertIn("m.rungs||0", js)
        self.assertIn("C.miniSparkline(t)", js)
        self.assertIn("makeWorker(id,t,index)", js)

    def test_history_archive_overlay_and_global_export_regressions(self) -> None:
        assets = Path(__file__).resolve().parents[1] / "src" / "ladder_climb" / "assets"
        html = (assets / "dashboard.html").read_text(encoding="utf-8")
        history = (assets / "history.js").read_text(encoding="utf-8")
        charts = (assets / "charts.js").read_text(encoding="utf-8")
        css = (assets / "dashboard.css").read_text(encoding="utf-8")
        for control in ("model-history", "campaign-strip", "model-history-summary", "global-history", "history-search", "history-status-filter", "history-review-filter", "export-json", "export-csv"):
            self.assertIn(f'id="{control}"', html)
        self.assertIn("Overlay Archives", history)
        self.assertIn("ladder.json?campaign=", history)
        self.assertIn("milestone('Baseline → best'", history)
        self.assertEqual(history.count("milestone("), 5)  # definition plus four summary cells
        self.assertIn("query({format:name})", history)
        self.assertIn("archive-frontier", charts)
        self.assertIn("stroke-dasharray:4 4", css)

    def test_dashboard_javascript_syntax(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        assets = Path(__file__).resolve().parents[1] / "src" / "ladder_climb" / "assets"
        for name in ("charts.js", "history.js", "dashboard.js"):
            with self.subTest(asset=name):
                result = subprocess.run([node, "--check", str(assets / name)], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

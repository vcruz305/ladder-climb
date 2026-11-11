from __future__ import annotations

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

    def test_dashboard_has_no_campaign_specific_track_names(self) -> None:
        assets = Path(__file__).resolve().parents[1] / "src" / "ladder_climb" / "assets"
        html = (assets / "dashboard.html").read_text(encoding="utf-8")
        js = (assets / "dashboard.js").read_text(encoding="utf-8")
        charts = (assets / "charts.js").read_text(encoding="utf-8")
        self.assertIn('id="track-filters"', html)
        self.assertIn("Object.entries(data.tracks)", js)
        self.assertIn("track.direction", charts)
        self.assertIn("America/Los_Angeles", html)


if __name__ == "__main__":
    unittest.main()

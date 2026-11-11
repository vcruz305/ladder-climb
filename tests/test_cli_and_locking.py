from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from ladder_climb.schema import ValidationError, champion, load_board, validate_board  # noqa: E402
from ladder_climb.server import make_server  # noqa: E402


def cli(board: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "ladder_climb", *args, "--dir", str(board)],
        text=True, capture_output=True, env=env, check=check, timeout=30,
    )


def worker(board: Path, index: int) -> None:
    rung = f"S-{index:02d}"
    cli(board, "rung", "--track", "speed", "--id", rung,
        "--status", "testing", "--value", "0", "--gate", "pending",
        "--summary", f"parallel candidate {index}", "--metric", "worker=" + str(index))
    time.sleep(0.08 + index * 0.005)
    kept = index == 7
    cli(board, "rung", "--track", "speed", "--id", rung,
        "--status", "kept" if kept else "rejected",
        "--value", "200" if kept else str(90 + index),
        "--gate", "pass", "--metric", "relative_error=0.0001")


class ConcurrentCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.board = Path(self.temp.name)
        cli(self.board, "init", "--title", "Concurrency Test", "--subtitle", "eight writers",
            "--track", "speed:Kernel Speed:tok/s:100:300:higher",
            "--track", "latency:Request Latency:ms:100:40:lower")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_eight_subprocesses_preserve_every_update_and_time_attempts(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "from test_cli_and_locking import worker;from pathlib import Path;"
            "worker(Path(sys.argv[2]),int(sys.argv[3]))"
        )
        processes = [subprocess.Popen(
            [sys.executable, "-c", code, str(ROOT / "tests"), str(self.board), str(i)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for i in range(8)]
        reads = 0
        while any(p.poll() is None for p in processes):
            with (self.board / "ladder.json").open(encoding="utf-8") as handle:
                json.load(handle)
            reads += 1
            time.sleep(0.005)
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertGreater(reads, 0)
        board = load_board(self.board)
        rungs = board["tracks"]["speed"]["rungs"]
        self.assertEqual(len(rungs), 8, "no concurrent update may be lost")
        self.assertEqual({r["id"] for r in rungs}, {f"S-{i:02d}" for i in range(8)})
        self.assertTrue(all(r["duration_s"] >= 0.07 for r in rungs))
        self.assertTrue(all(r["started_at"] != r["updated_at"] for r in rungs))
        self.assertEqual(champion(board["tracks"]["speed"])[0], 200)
        cli(self.board, "rung", "--track", "speed", "--id", "S-08",
            "--status", "kept", "--value", "250", "--gate", "pass")
        cli(self.board, "rung", "--track", "latency", "--id", "L-01",
            "--status", "kept", "--value", "80", "--gate", "pass")
        board = load_board(self.board)
        self.assertEqual(champion(board["tracks"]["speed"])[0], 250)
        self.assertEqual(champion(board["tracks"]["latency"])[0], 80)
        self.assertIn("2 track(s), 10 rung(s)", cli(self.board, "validate").stdout)
        status = cli(self.board, "status").stdout
        self.assertIn("250 tok/s", status)
        self.assertIn("80 ms", status)
        self.assertIn("rejected: 7", status)

    def test_http_dashboard_feed_and_health(self) -> None:
        cli(self.board, "rung", "--track", "speed", "--id", "HTTP-1",
            "--status", "testing", "--value", "0", "--summary", "server check")
        server = make_server(self.board, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            for route, marker in (("/", b"Ladder Climb"),
                                  ("/ladder.json", b"Concurrency Test"),
                                  ("/api/health", b'"ok": true'),
                                  ("/assets/dashboard.js", b"setInterval(poll,2000)")):
                with urllib.request.urlopen(base + route, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(marker, response.read())
                    self.assertIn("no-store", response.headers["Cache-Control"])
            with urllib.request.urlopen(base + "/api/health") as response:
                health = json.load(response)
            self.assertEqual(health["tracks"], 2)
            self.assertEqual(health["rungs"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_schema_rejects_invalid_gate_and_regression(self) -> None:
        board = load_board(self.board)
        rung = {"id": "BAD", "status": "kept", "value": 50, "unit": "tok/s",
                "summary": "invalid", "gate": "fail", "metrics": {}}
        board["tracks"]["speed"]["rungs"] = [rung]
        with self.assertRaises(ValidationError):
            validate_board(board)
        rung["gate"] = "pass"
        with self.assertRaises(ValidationError):
            validate_board(board)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Split literals keep this scanner from matching its own source.
FORBIDDEN = (
    "dm" + "l",
    "dark " + "matter",
    "git" + "ea",
    "victor" + "cruz",
    "172." + "23.",
    "100." + "111.",
    "tailda" + "7808",
    "cruz" + "spark",
    "darks" + "mac",
    "sage-" + "rexl3",
)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True,
                          capture_output=True, check=True, timeout=30)


def violations(text: str) -> list[str]:
    lowered = text.lower()
    return [token for token in FORBIDDEN if token in lowered]


class PublicHygieneTests(unittest.TestCase):
    def test_every_tracked_path_and_file_is_public_safe(self) -> None:
        tracked = [Path(p) for p in git("ls-files", "-z").stdout.split("\0") if p]
        self.assertTrue(tracked, "expected a Git-tracked source tree")
        failures: list[str] = []
        for relative in tracked:
            found = violations(str(relative))
            path = ROOT / relative
            if path.is_file():
                found += violations(path.read_text(encoding="utf-8", errors="replace"))
            if found:
                failures.append(f"{relative}: {', '.join(sorted(set(found)))}")
        self.assertFalse(failures, "Forbidden public content:\n" + "\n".join(failures))

    def test_every_commit_message_is_public_safe(self) -> None:
        commits = git("rev-list", "HEAD").stdout.splitlines()
        self.assertTrue(commits)
        failures: list[str] = []
        for commit in commits:
            message = git("show", "-s", "--format=%B", commit).stdout
            found = violations(message)
            if found:
                failures.append(f"{commit}: {', '.join(found)}")
        self.assertFalse(failures, "Forbidden commit content:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()

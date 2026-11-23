#!/usr/bin/env python3
"""Cross-platform CI driver: install the fixture manifest with the real CLI, then
assert the expected result tree.

Runs ``python -m szcdfi`` in a subprocess with an isolated HOME (so the run is
hermetic on every OS), then reuses ``assert_fixture_tree`` to verify the tree.
Exits non-zero on any failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import assert_fixture_tree  # same directory (tests/)

PKG = Path(__file__).parent / "fixtures" / "pkg"


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))

        result = subprocess.run(
            [
                sys.executable, "-m", "szcdfi",
                "--package-dir", str(PKG),
                "--guard", "bash",
                "-I",
            ],
            env=env,
        )
        if result.returncode != 0:
            print(f"szcdfi exited with {result.returncode}")
            return result.returncode

        errors = assert_fixture_tree.check(home, PKG)
        if errors:
            print("CI FIXTURE TREE ASSERTION FAILED:")
            for err in errors:
                print(f"  - {err}")
            return 1

        print("CI fixture result tree OK.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

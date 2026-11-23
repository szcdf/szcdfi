"""End-to-end CLI tests: run ``szcdfi`` against the fixture manifest and assert
the full result tree (the same assertion CI uses)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from szcdfi import cli

sys.path.insert(0, str(Path(__file__).parent))
import assert_fixture_tree  # noqa: E402

FIXTURE_PKG = Path(__file__).parent / "fixtures" / "pkg"


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_cli_installs_fixture_tree(fake_home: Path):
    rc = cli.main(
        ["--package-dir", str(FIXTURE_PKG), "--guard", "bash", "-I"]
    )
    assert rc == 0
    errors = assert_fixture_tree.check(fake_home, FIXTURE_PKG)
    assert errors == [], errors


def test_cli_dry_run_changes_nothing(fake_home: Path):
    rc = cli.main(
        ["--package-dir", str(FIXTURE_PKG), "--guard", "bash", "--dry-run"]
    )
    assert rc == 0
    # Config root may have been created by resolution, but no managed files.
    assert not (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").exists()
    assert not (fake_home / ".bashrc").exists()


def test_cli_rerun_is_idempotent(fake_home: Path):
    args = ["--package-dir", str(FIXTURE_PKG), "--guard", "bash", "-I"]
    assert cli.main(args) == 0
    bashrc_first = (fake_home / ".bashrc").read_bytes()
    assert cli.main(args) == 0
    assert (fake_home / ".bashrc").read_bytes() == bashrc_first


def test_cli_pwsh_guard_installs_pwsh_file(fake_home: Path):
    rc = cli.main(
        ["--package-dir", str(FIXTURE_PKG), "--guard", "pwsh", "-I"]
    )
    assert rc == 0
    cr = fake_home / ".config" / "szcdf"
    assert (cr / "bin" / "pwsh-only.ps1").is_file()
    assert not (cr / "bin" / "bash-only.sh").exists()


def test_cli_missing_spec_errors(tmp_path: Path, fake_home: Path):
    rc = cli.main(["--package-dir", str(tmp_path / "nope"), "-I"])
    assert rc == 1

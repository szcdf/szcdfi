"""Tests for the interactive CLI paths (confirm, custom mode, abort) and for
package entry points."""

from __future__ import annotations

from pathlib import Path

import pytest

from szcdfi import cli

FIXTURE_PKG = Path(__file__).parent / "fixtures" / "pkg"


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _args(*extra: str) -> list[str]:
    return ["--package-dir", str(FIXTURE_PKG), "--guard", "bash", *extra]


def test_quick_interactive_confirm_yes_installs(fake_home, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")
    assert cli.main(_args()) == 0
    assert (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").is_file()


def test_quick_interactive_confirm_blank_defaults_yes(fake_home, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    assert cli.main(_args()) == 0
    assert (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").is_file()


def test_quick_interactive_confirm_no_aborts(fake_home, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")
    assert cli.main(_args()) == 1
    assert not (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").exists()


def test_confirm_eof_treated_as_no(fake_home, monkeypatch):
    def _raise(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)
    assert cli.main(_args()) == 1


def test_custom_mode_runs_each_confirmed_step(fake_home, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")
    assert cli.main(_args("-m", "custom")) == 0
    assert (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").is_file()


def test_custom_mode_skips_declined_steps(fake_home, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")
    assert cli.main(_args("-m", "custom")) == 0  # skipping is not an error
    assert not (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").exists()


def test_no_active_directives_is_a_noop(fake_home, tmp_path):
    # A manifest with only guarded lines, none matching -> empty plan.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / ".szcdfis").write_text(
        "#@pwsh COPY a b\n# just a comment\n", encoding="utf-8"
    )
    rc = cli.main(["--package-dir", str(pkg), "--guard", "bash", "-I"])
    assert rc == 0
    assert not (fake_home / ".bashrc").exists()


def test_resolve_pkg_and_spec_variants(tmp_path):
    pkg = tmp_path / "proj"
    (pkg / "sub").mkdir(parents=True)
    spec = pkg / ".szcdfis"
    spec.write_text("# empty\n", encoding="utf-8")

    # spec only -> package dir is the spec's grandparent.
    p, s = cli.resolve_pkg_and_spec(None, str(spec), start_dir=tmp_path)
    assert s == spec and p == spec.resolve().parent.parent

    # pkg only -> spec is <pkg>/.szcdfis.
    p, s = cli.resolve_pkg_and_spec(str(pkg), None, start_dir=tmp_path)
    assert p == pkg and s == pkg / ".szcdfis"

    # neither -> walk up from start_dir.
    p, s = cli.resolve_pkg_and_spec(None, None, start_dir=pkg / "sub")
    assert s == pkg / ".szcdfis"


def test_resolve_pkg_and_spec_not_found(tmp_path):
    from szcdfi.engine import SpecError

    with pytest.raises(SpecError):
        cli.resolve_pkg_and_spec(None, None, start_dir=tmp_path)
    with pytest.raises(SpecError):
        cli.resolve_pkg_and_spec(None, str(tmp_path / "missing.szcdfis"),
                                 start_dir=tmp_path)
    with pytest.raises(SpecError):
        cli.resolve_pkg_and_spec(str(tmp_path / "nopkg"), None, start_dir=tmp_path)


def test_explicit_pkg_and_spec(fake_home):
    rc = cli.main(
        [
            "--package-dir", str(FIXTURE_PKG),
            "--spec", str(FIXTURE_PKG / ".szcdfis"),
            "--guard", "bash", "-I",
        ]
    )
    assert rc == 0
    assert (fake_home / ".config" / "szcdf" / "bin" / "hello.sh").is_file()


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "szcdfi" in out


def test_main_module_imports():
    # Covers src/szcdfi/__main__.py (its run guard is excluded from coverage).
    import szcdfi.__main__ as entry

    assert entry.main is cli.main

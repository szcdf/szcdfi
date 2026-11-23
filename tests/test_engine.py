"""Tests for the directive engine: config root, path resolution, and the four
directives applied end to end."""

from __future__ import annotations

from pathlib import Path

import pytest

from szcdfi import textutil
from szcdfi.engine import (
    Installer,
    SpecError,
    default_guards,
    resolve_config_root,
    resolve_dest,
)


# --- config root resolution ------------------------------------------------ #


def test_config_root_prefers_existing_dot_config(tmp_path: Path):
    (tmp_path / ".config" / "szcdf").mkdir(parents=True)
    assert resolve_config_root(tmp_path) == tmp_path / ".config" / "szcdf"


def test_config_root_falls_back_to_dot_szcdf(tmp_path: Path):
    (tmp_path / ".szcdf").mkdir()
    assert resolve_config_root(tmp_path) == tmp_path / ".szcdf"


def test_config_root_creates_dot_config_when_neither_exists(tmp_path: Path):
    root = resolve_config_root(tmp_path)
    assert root == tmp_path / ".config" / "szcdf"
    assert root.is_dir()


def test_config_root_dot_config_is_file_falls_back_to_dot_szcdf(tmp_path: Path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "szcdf").write_text("not a dir", encoding="utf-8")
    root = resolve_config_root(tmp_path)
    assert root == tmp_path / ".szcdf"
    assert root.is_dir()


# --- destination path resolution ------------------------------------------ #


def test_resolve_dest_substitutes_config_root_and_home(tmp_path: Path):
    cr = tmp_path / "cfg"
    home = tmp_path / "home"
    assert resolve_dest("$CONFIG_ROOT/modules", cr, home) == cr / "modules"
    assert resolve_dest("$HOME/.bashrc", cr, home) == home / ".bashrc"


def test_resolve_dest_supports_extra_vars_like_profile(tmp_path: Path):
    cr = tmp_path / "cfg"
    home = tmp_path / "home"
    profile = str(home / "Documents" / "profile.ps1")
    out = resolve_dest("$PROFILE", cr, home, extra={"PROFILE": profile})
    assert out == Path(profile)


def test_resolve_dest_leaves_unknown_token_verbatim(tmp_path: Path):
    out = resolve_dest("$NOPE/x", tmp_path, tmp_path)
    assert out.name == "x"
    assert "$NOPE" in str(out)


def test_default_guards_are_platform_sensible():
    guards = default_guards()
    assert guards  # non-empty
    assert guards & {"bash", "pwsh"}  # includes a shell token for this platform


# --- fixtures for directive application ------------------------------------ #


@pytest.fixture
def world(tmp_path: Path):
    """A package dir + home + config root to install into."""
    pkg = tmp_path / "pkg"
    home = tmp_path / "home"
    pkg.mkdir()
    home.mkdir()
    config_root = resolve_config_root(home)
    return pkg, home, config_root


def make_installer(pkg, home, config_root, **kw) -> Installer:
    logs: list[str] = []
    inst = Installer(
        pkg_dir=pkg,
        config_root=config_root,
        home=home,
        guards={"bash", "linux"},
        logger=logs.append,
        **kw,
    )
    inst.logs = logs  # type: ignore[attr-defined]
    return inst


# --- COPY ------------------------------------------------------------------ #


def test_copy_file(world):
    pkg, home, cr = world
    (pkg / "bin").mkdir()
    (pkg / "bin" / "x.sh").write_text("echo hi\n", encoding="utf-8")
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["COPY bin/x.sh $CONFIG_ROOT/bin/x.sh"])
    out = cr / "bin" / "x.sh"
    assert out.read_text(encoding="utf-8") == "echo hi\n"


def test_copy_is_idempotent_and_skips_identical(world):
    pkg, home, cr = world
    (pkg / "f").write_text("same\n", encoding="utf-8")
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["COPY f $CONFIG_ROOT/f"])
    inst.apply_lines(["COPY f $CONFIG_ROOT/f"])
    assert any("identical" in m for m in inst.logs)


def test_copy_missing_source_is_skipped_not_fatal(world):
    pkg, home, cr = world
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["COPY does/not/exist $CONFIG_ROOT/x"])
    assert any("source not found" in m.lower() for m in inst.logs)
    assert not (cr / "x").exists()


# --- COPYALL --------------------------------------------------------------- #


def test_copyall_copies_each_direct_child(world):
    pkg, home, cr = world
    src = pkg / "src" / "core-modules"
    src.mkdir(parents=True)
    (src / "a.sh").write_text("a\n", encoding="utf-8")
    (src / "b.sh").write_text("b\n", encoding="utf-8")
    sub = src / "sub"
    sub.mkdir()
    (sub / "c.sh").write_text("c\n", encoding="utf-8")
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["COPYALL src/core-modules $CONFIG_ROOT/modules"])
    assert (cr / "modules" / "a.sh").read_text(encoding="utf-8") == "a\n"
    assert (cr / "modules" / "b.sh").read_text(encoding="utf-8") == "b\n"
    # Directory children are copied recursively as a unit.
    assert (cr / "modules" / "sub" / "c.sh").read_text(encoding="utf-8") == "c\n"


def test_copyall_missing_source_dir_is_fatal(world):
    pkg, home, cr = world
    inst = make_installer(pkg, home, cr)
    with pytest.raises(SpecError):
        inst.apply_lines(["COPYALL src/missing $CONFIG_ROOT/x"])


# --- PREPENDTEXT / APPENDTEXT ---------------------------------------------- #


def test_prependtext_into_home_rc(world):
    pkg, home, cr = world
    entry = pkg / "src" / "core-entries"
    entry.mkdir(parents=True)
    (entry / "entry-bash.sh").write_text("source szcdf\n", encoding="utf-8")
    (home / ".bashrc").write_text("export PATH=/x\n", encoding="utf-8")
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(
        ["PREPENDTEXT src/core-entries/entry-bash.sh $HOME/.bashrc ENTRY-BASH"]
    )
    lines = (home / ".bashrc").read_text(encoding="utf-8").splitlines()
    begin, end = textutil.section_markers("#", "ENTRY-BASH")
    assert lines[0] == begin
    assert "source szcdf" in lines
    assert lines[-1] == "export PATH=/x"


def test_appendtext_creates_missing_dest(world):
    pkg, home, cr = world
    src = pkg / "s.txt"
    src.write_text("body\n", encoding="utf-8")
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["APPENDTEXT s.txt $HOME/.profile SEC"])
    out = home / ".profile"
    assert out.is_file()
    begin, end = textutil.section_markers("#", "SEC")
    text = out.read_text(encoding="utf-8")
    assert begin in text and end in text and "body" in text


def test_prependtext_custom_comment_indicator(world):
    pkg, home, cr = world
    src = pkg / "s"
    src.write_text("x\n", encoding="utf-8")
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["PREPENDTEXT s $HOME/.config/app.conf SEC //"])
    text = (home / ".config" / "app.conf").read_text(encoding="utf-8")
    assert "// >>>>>>> SZCDF_GENERATED_TEXT // BEGIN SECTION_ID=SEC" in text


def test_prependtext_missing_source_is_fatal(world):
    pkg, home, cr = world
    inst = make_installer(pkg, home, cr)
    with pytest.raises(SpecError):
        inst.apply_lines(["PREPENDTEXT nope $HOME/.bashrc SEC"])


# --- unknown directive ----------------------------------------------------- #


def test_unknown_directive_is_warned_not_fatal(world):
    pkg, home, cr = world
    inst = make_installer(pkg, home, cr)
    inst.apply_lines(["FROBNICATE a b"])
    assert any("unknown directive" in m.lower() for m in inst.logs)

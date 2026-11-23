"""Edge-case tests for the engine: editable/symlink mode, replace semantics, and
preview strings."""

from __future__ import annotations

from pathlib import Path

import pytest

from szcdfi.engine import Installer, resolve_config_root
from szcdfi.manifest import Directive


def _can_symlink(tmp_path: Path) -> bool:
    target = tmp_path / "_t"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "_l"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return False
    link.unlink()
    return True


@pytest.fixture
def world(tmp_path: Path):
    pkg = tmp_path / "pkg"
    home = tmp_path / "home"
    pkg.mkdir()
    home.mkdir()
    return pkg, home, resolve_config_root(home)


def make(pkg, home, cr, **kw) -> Installer:
    logs: list[str] = []
    inst = Installer(
        pkg_dir=pkg, config_root=cr, home=home,
        guards={"bash"}, logger=logs.append, **kw,
    )
    inst.logs = logs  # type: ignore[attr-defined]
    return inst


def test_editable_creates_symlink_and_replaces_existing(world, tmp_path):
    if not _can_symlink(tmp_path):
        pytest.skip("symlinks not permitted on this platform")
    pkg, home, cr = world
    (pkg / "f").write_text("v\n", encoding="utf-8")
    inst = make(pkg, home, cr, editable=True)
    inst.apply_lines(["COPY f $CONFIG_ROOT/f"])
    link = cr / "f"
    assert link.is_symlink()
    # Re-run replaces the existing link cleanly.
    inst.apply_lines(["COPY f $CONFIG_ROOT/f"])
    assert link.is_symlink()
    assert link.resolve() == (pkg / "f").resolve()


def test_copy_replaces_existing_directory_with_file(world):
    pkg, home, cr = world
    (pkg / "f").write_text("file\n", encoding="utf-8")
    # Destination currently a directory -> must be replaced by the file.
    (cr / "f").mkdir()
    (cr / "f" / "junk").write_text("junk\n", encoding="utf-8")
    inst = make(pkg, home, cr)
    inst.apply_lines(["COPY f $CONFIG_ROOT/f"])
    assert (cr / "f").is_file()
    assert (cr / "f").read_text(encoding="utf-8") == "file\n"


def test_copy_directory_replaces_existing_directory(world):
    pkg, home, cr = world
    src = pkg / "d"
    src.mkdir()
    (src / "a").write_text("a\n", encoding="utf-8")
    dest = cr / "d"
    dest.mkdir()
    (dest / "old").write_text("old\n", encoding="utf-8")
    inst = make(pkg, home, cr)
    inst.apply_lines(["COPY d $CONFIG_ROOT/d"])
    assert (dest / "a").is_file()
    assert not (dest / "old").exists()  # dest became src (cp -T semantics)


def test_copy_replaces_symlink_with_regular_file(world, tmp_path):
    if not _can_symlink(tmp_path):
        pytest.skip("symlinks not permitted on this platform")
    pkg, home, cr = world
    (pkg / "f").write_text("real\n", encoding="utf-8")
    other = pkg / "other"
    other.write_text("other\n", encoding="utf-8")
    (cr).mkdir(parents=True, exist_ok=True)
    (cr / "f").symlink_to(other)
    inst = make(pkg, home, cr)
    inst.apply_lines(["COPY f $CONFIG_ROOT/f"])
    assert (cr / "f").is_file()
    assert not (cr / "f").is_symlink()
    assert (cr / "f").read_text(encoding="utf-8") == "real\n"


def test_preview_strings_cover_all_directives(world):
    pkg, home, cr = world
    inst = make(pkg, home, cr)
    assert "Copy file" in inst.preview(Directive("COPY", ["a", "b"], "COPY a b"))
    assert "Copy all" in inst.preview(Directive("COPYALL", ["a", "b"], "x"))
    assert "Prepend" in inst.preview(
        Directive("PREPENDTEXT", ["a", "b", "ID"], "x")
    )
    assert "Append" in inst.preview(
        Directive("APPENDTEXT", ["a", "b", "ID"], "x")
    )
    assert "Unknown" in inst.preview(Directive("NOPE", [], "NOPE"))


def test_preview_editable_says_link(world):
    pkg, home, cr = world
    inst = make(pkg, home, cr, editable=True)
    assert "Link file" in inst.preview(Directive("COPY", ["a", "b"], "x"))


def test_preview_missing_args_are_reported(world):
    pkg, home, cr = world
    inst = make(pkg, home, cr)
    assert "missing args" in inst.preview(Directive("COPY", ["a"], "COPY a"))
    assert "missing args" in inst.preview(Directive("COPYALL", [], "COPYALL"))
    assert "missing args" in inst.preview(
        Directive("PREPENDTEXT", ["a", "b"], "x")
    )


def test_execute_missing_args_warns_not_raises(world):
    pkg, home, cr = world
    inst = make(pkg, home, cr)
    inst.apply_lines(["COPY onlyone"])
    inst.apply_lines(["COPYALL onlyone"])
    assert any("COPY needs" in m for m in inst.logs)
    assert any("COPYALL needs" in m for m in inst.logs)

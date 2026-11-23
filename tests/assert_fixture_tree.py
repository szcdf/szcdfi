#!/usr/bin/env python3
"""Assert the result tree produced by installing tests/fixtures/pkg/.szcdfis
with ``--guard bash``.

Usage: assert_fixture_tree.py <home_dir> <pkg_dir>

Used both by the CLI integration test and by the cross-platform CI matrix, so
the expected tree is asserted identically everywhere. Exits non-zero on the
first failed assertion.
"""

from __future__ import annotations

import sys
from pathlib import Path

BEGIN = (
    "# >>>>>>> SZCDF_GENERATED_TEXT // BEGIN SECTION_ID=ENTRY-BASH "
    "// DO NOT EDIT MANUALLY"
)
END = (
    "# <<<<<<< SZCDF_GENERATED_TEXT // END SECTION_ID=ENTRY-BASH "
    "// DO NOT EDIT MANUALLY"
)


def check(home: Path, pkg: Path) -> list[str]:
    errors: list[str] = []
    config_root = home / ".config" / "szcdf"

    def want_file(path: Path, expected_source: Path | None = None) -> None:
        if not path.is_file():
            errors.append(f"missing file: {path}")
            return
        if expected_source is not None:
            if path.read_bytes() != expected_source.read_bytes():
                errors.append(f"content mismatch: {path} != {expected_source}")

    def want_absent(path: Path) -> None:
        if path.exists():
            errors.append(f"should not exist: {path}")

    def no_bom(path: Path) -> None:
        if path.is_file() and path.read_bytes().startswith(b"\xef\xbb\xbf"):
            errors.append(f"unexpected BOM: {path}")

    # COPY
    want_file(config_root / "bin" / "hello.sh", pkg / "bin" / "hello.sh")

    # COPYALL (each direct child)
    want_file(config_root / "modules" / "10-env.sh",
              pkg / "src" / "core-modules" / "10-env.sh")
    want_file(config_root / "modules" / "20-aliases.sh",
              pkg / "src" / "core-modules" / "20-aliases.sh")

    # Guards: bash active, pwsh inert
    want_file(config_root / "bin" / "bash-only.sh", pkg / "bin" / "bash-only.sh")
    want_absent(config_root / "bin" / "pwsh-only.ps1")

    # PREPENDTEXT into a (new) .bashrc
    bashrc = home / ".bashrc"
    want_file(bashrc)
    no_bom(bashrc)
    if bashrc.is_file():
        lines = bashrc.read_text(encoding="utf-8").split("\n")
        if not lines or lines[0] != BEGIN:
            errors.append(f".bashrc does not start with the BEGIN marker")
        if END not in lines:
            errors.append(f".bashrc missing END marker on its own line")
        if "export SZCDF_CONFIG_ROOT=\"${HOME}/.config/szcdf\"" not in lines:
            errors.append(".bashrc missing entry content")

    # APPENDTEXT into a (new) .profile
    profile = home / ".profile"
    want_file(profile)
    no_bom(profile)
    if profile.is_file():
        lines = profile.read_text(encoding="utf-8").split("\n")
        if END not in lines:
            errors.append(".profile missing END marker on its own line")
        if BEGIN not in lines:
            errors.append(".profile missing BEGIN marker")

    return errors


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    home = Path(sys.argv[1])
    pkg = Path(sys.argv[2])
    errors = check(home, pkg)
    if errors:
        print("FIXTURE TREE ASSERTION FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Fixture result tree OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line interface for szcdfi.

Run via ``uvx szcdfi@latest`` (ephemeral), ``uv tool install szcdfi`` (a
persistent shim), ``szcdfi`` (installed), or ``python -m szcdfi``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .engine import Installer, SpecError, default_guards, resolve_config_root

SPEC_NAME = ".szcdfis"


def _default_spec_for(pkg_dir: Path) -> Path:
    return pkg_dir / SPEC_NAME


def resolve_pkg_and_spec(
    pkg_dir: str | None,
    spec: str | None,
    start_dir: Path,
) -> tuple[Path, Path]:
    """Resolve (package_dir, spec_file), mirroring the Bash installer.

    * spec only  -> package dir is the spec's grandparent (``dirname/dirname``).
    * pkg only   -> spec is ``<pkg>/.szcdfis``.
    * neither    -> start at ``start_dir`` and walk up ancestors until a
      ``.szcdfis`` is found.
    """
    if spec and not pkg_dir:
        spec_path = Path(spec).expanduser()
        if not spec_path.is_file():
            raise SpecError(f"Install spec not found: {spec_path}")
        return spec_path.resolve().parent.parent, spec_path

    if pkg_dir and not spec:
        pkg = Path(pkg_dir).expanduser()
        spec_path = _default_spec_for(pkg)
        if not spec_path.is_file():
            raise SpecError(
                f"Could not find {SPEC_NAME} in package dir {pkg}."
            )
        return pkg, spec_path

    if pkg_dir and spec:
        return Path(pkg_dir).expanduser(), Path(spec).expanduser()

    # Neither: walk up from start_dir looking for a .szcdfis.
    pkg = start_dir.resolve()
    while True:
        spec_path = _default_spec_for(pkg)
        if spec_path.is_file():
            return pkg, spec_path
        parent = pkg.parent
        if parent == pkg:
            raise SpecError(
                f"Could not find {SPEC_NAME} in {start_dir} or any parent directory."
            )
        pkg = parent


def _confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [Y/n]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="szcdfi",
        description=(
            "Cross-platform installer for the szcdf dotfiles framework. "
            "Reads a .szcdfis manifest and applies COPY, COPYALL, PREPENDTEXT "
            "and APPENDTEXT directives with uniform, correct text handling."
        ),
    )
    parser.add_argument(
        "-p", "--package-dir", dest="package_dir",
        help="Directory containing the szcdf package. Defaults to the current "
             "directory (searched upward for a .szcdfis).",
    )
    parser.add_argument(
        "-s", "--spec", dest="spec",
        help="The install spec (.szcdfis) file to use.",
    )
    parser.add_argument(
        "-m", "--mode", choices=("quick", "custom"), default="quick",
        help="quick: preview all, confirm once, apply. "
             "custom: preview and confirm each step. Default: quick.",
    )
    parser.add_argument(
        "-I", "--non-interactive", dest="non_interactive", action="store_true",
        help="Apply without prompting (required for unattended / CI runs).",
    )
    parser.add_argument(
        "-e", "--editable", action="store_true",
        help="Symlink instead of copying files (for development).",
    )
    parser.add_argument(
        "-g", "--guard", dest="guards", action="append", metavar="ID",
        help="Guard token this installer answers to (repeatable). Overrides the "
             "platform default. A `#@<ID> ...` manifest line is active only when "
             "<ID> is in the active guard set.",
    )
    parser.add_argument(
        "-n", "--dry-run", dest="dry_run", action="store_true",
        help="Preview the plan without changing anything.",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"szcdfi {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = Path.home()

    try:
        config_root = resolve_config_root(home)
        pkg_dir, spec = resolve_pkg_and_spec(
            args.package_dir, args.spec, start_dir=Path.cwd()
        )
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    guards = set(args.guards) if args.guards else default_guards()

    installer = Installer(
        pkg_dir=pkg_dir,
        config_root=config_root,
        home=home,
        guards=guards,
        editable=args.editable,
        logger=lambda msg: print(f"  {msg}"),
    )

    print("=== Stephen's dotfiles (szcdfi) ===")
    print(f"Package dir : {pkg_dir}")
    print(f"Spec file   : {spec}")
    print(f"Config root : {config_root}")
    print(f"Guards      : {', '.join(sorted(guards))}")
    print(f"Mode        : {args.mode}{' (editable/symlink)' if args.editable else ''}")
    print()

    plan = installer.plan(spec)
    if not plan:
        print("No active directives in the manifest for these guards. Nothing to do.")
        return 0

    print("The installer will make the following changes:")
    for step, directive in enumerate(plan, 1):
        print(f"[Step {step}] {installer.preview(directive)}")
    print()

    if args.dry_run:
        print("Dry run: no changes made.")
        return 0

    interactive = not args.non_interactive

    try:
        if args.mode == "custom" and interactive:
            for step, directive in enumerate(plan, 1):
                print(f"[Step {step}] {installer.preview(directive)}")
                if not _confirm("Run?"):
                    print("  skipped")
                    continue
                installer.execute(directive)
        else:
            if interactive and not _confirm("Continue with the install?"):
                print("Aborting install....")
                return 1
            print("Installing...")
            for directive in plan:
                installer.execute(directive)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print()
    print("Installation was successful!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

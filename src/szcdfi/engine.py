"""The directive engine: config-root resolution, path resolution, and the four
install directives (COPY, COPYALL, PREPENDTEXT, APPENDTEXT).

Text-writing directives delegate to :mod:`szcdfi.textutil` so the BOM-free /
EOL-preserving / marker-format rules live in exactly one place.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import manifest, textutil
from .manifest import Directive

DEFAULT_COMMENT = "#"

# `$NAME` or `${NAME}` token for destination-path resolution.
_VAR_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")


class SpecError(Exception):
    """A fatal problem applying the manifest."""


def default_guards() -> set[str]:
    """The guard set this platform's installer answers to by default.

    One engine stands in for every shell on the host, so it matches the guards
    for the shells and platform tokens that make sense here. Override with
    ``--guard`` on the CLI (or ``guards=`` in code) to narrow or redirect it.
    """
    system = platform.system().lower()
    if system == "windows":
        return {"pwsh", "powershell", "windows", "nt", "win"}
    guards = {"bash", "sh", "zsh", "posix", "unix"}
    if system == "darwin":
        guards |= {"darwin", "macos", "mac", "osx"}
    elif system == "linux":
        guards |= {"linux"}
    else:
        guards |= {system}
    return guards


def resolve_config_root(home: Path) -> Path:
    """Resolve ``$CONFIG_ROOT`` (``~/.config/szcdf`` or ``~/.szcdf``).

    Ports the Bash installer's resolution, including its edge cases:
    prefer an existing ``~/.config/szcdf`` dir, else an existing ``~/.szcdf``
    dir; if ``~/.config/szcdf`` exists but is not a directory while ``~/.szcdf``
    also exists, that is fatal; if only ``~/.config/szcdf`` exists (not a dir),
    create and use ``~/.szcdf``; otherwise create and use ``~/.config/szcdf``.
    """
    dot_config = home / ".config" / "szcdf"
    dot_szcdf = home / ".szcdf"
    if dot_config.is_dir():
        return dot_config
    if dot_szcdf.is_dir():
        return dot_szcdf
    if dot_config.exists() and dot_szcdf.exists():
        raise SpecError(
            f"SZCDF config directory {dot_config} exists and is not a directory!"
        )
    if dot_config.exists():
        dot_szcdf.mkdir(parents=True, exist_ok=True)
        return dot_szcdf
    dot_config.mkdir(parents=True, exist_ok=True)
    return dot_config


def resolve_dest(
    raw: str,
    config_root: Path,
    home: Path,
    extra: dict[str, str] | None = None,
) -> Path:
    """Resolve a destination path, substituting ``$CONFIG_ROOT`` and ``$HOME``.

    Any further ``$VAR`` / ``${VAR}`` resolves from ``extra`` then the
    environment (e.g. ``$PROFILE`` when a guarded line targets it); an unknown
    token is left verbatim, as the Bash installer leaves it. ``~`` is expanded.
    """
    tokens = {"CONFIG_ROOT": str(config_root), "HOME": str(home)}
    if extra:
        tokens.update(extra)

    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        if name in tokens:
            return tokens[name]
        return os.environ.get(name, match.group(0))

    return Path(_VAR_RE.sub(repl, raw)).expanduser()


def _files_identical(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


@dataclass
class Installer:
    """Applies a parsed manifest into the resolved config root / home."""

    pkg_dir: Path
    config_root: Path
    home: Path
    guards: set[str]
    editable: bool = False
    logger: Callable[[str], None] = field(default=lambda msg: None)
    extra_vars: dict[str, str] = field(default_factory=dict)

    # -- planning --------------------------------------------------------- #

    def plan(self, spec_path: Path) -> list[Directive]:
        """Parse ``spec_path`` into the active directives for these guards."""
        lines = textutil.read_text_lines(spec_path)
        return list(manifest.iter_directives(lines, self.guards))

    def plan_lines(self, lines: list[str]) -> list[Directive]:
        """Parse in-memory manifest ``lines`` into active directives."""
        return list(manifest.iter_directives(lines, self.guards))

    def _dest(self, raw: str) -> Path:
        return resolve_dest(raw, self.config_root, self.home, self.extra_vars)

    # -- previewing ------------------------------------------------------- #

    def preview(self, directive: Directive) -> str:
        """A one-line, human-readable description of what a directive will do."""
        name, args = directive.name, directive.args
        verb = "Link" if self.editable else "Copy"
        if name == "COPY":
            if len(args) < 2:
                return f"COPY: missing args (needs <source> <dest>)"
            return f"{verb} file(s) from {self.pkg_dir / args[0]} to {self._dest(args[1])}"
        if name == "COPYALL":
            if len(args) < 2:
                return f"COPYALL: missing args (needs <source_dir> <dest_dir>)"
            return (
                f"{verb} all file(s) from {self.pkg_dir / args[0]} "
                f"to {self._dest(args[1])}"
            )
        if name in ("PREPENDTEXT", "APPENDTEXT"):
            if len(args) < 3:
                return f"{name}: missing args (needs <source> <dest> <section_id>)"
            where = "Prepend" if name == "PREPENDTEXT" else "Append"
            return (
                f"{where} text from {self.pkg_dir / args[0]} to {self._dest(args[1])} "
                f"with ID={args[2]} if section doesn't exist."
            )
        return f"Unknown directive {name!r} will be ignored."

    # -- executing -------------------------------------------------------- #

    def execute(self, directive: Directive) -> None:
        """Apply a single directive. Unknown directives are warned and skipped."""
        handler = {
            "COPY": self._copy,
            "COPYALL": self._copyall,
            "PREPENDTEXT": self._prependtext,
            "APPENDTEXT": self._appendtext,
        }.get(directive.name)
        if handler is None:
            self.logger(f"Unknown directive {directive.name!r} will be ignored.")
            return
        handler(directive.args)

    def apply(self, spec_path: Path) -> list[Directive]:
        """Plan then execute every active directive. Returns the plan."""
        return self._run(self.plan(spec_path))

    def apply_lines(self, lines: list[str]) -> list[Directive]:
        """Plan then execute every active directive from in-memory ``lines``."""
        return self._run(self.plan_lines(lines))

    def _run(self, plan: list[Directive]) -> list[Directive]:
        for directive in plan:
            self.execute(directive)
        return plan

    # -- directive handlers ---------------------------------------------- #

    def _copy(self, args: list[str]) -> None:
        if len(args) < 2:
            self.logger("COPY needs <source> <dest>. Skipping.")
            return
        src = self.pkg_dir / args[0]
        dest = self._dest(args[1])
        if not (src.exists() or src.is_symlink()):
            self.logger(f"COPY source not found: {src}. Skipping.")
            return
        self._copy_one(src, dest)

    def _copyall(self, args: list[str]) -> None:
        if len(args) < 2:
            self.logger("COPYALL needs <source_dir> <dest_dir>. Skipping.")
            return
        src_dir = self.pkg_dir / args[0]
        dest_dir_raw = args[1].rstrip("/")
        if not src_dir.is_dir():
            raise SpecError(f"Source directory not found: {src_dir}")
        # Non-recursive: COPY each direct child (file or directory) by name.
        for child in sorted(src_dir.iterdir(), key=lambda p: p.name):
            dest = self._dest(f"{dest_dir_raw}/{child.name}")
            self._copy_one(child, dest)

    def _copy_one(self, src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)

        if self.editable:
            if dest.exists() or dest.is_symlink():
                _remove(dest)
            dest.symlink_to(src)
            self.logger(f"linked  {dest} -> {src}")
            return

        if src.is_dir():
            if dest.exists() or dest.is_symlink():
                _remove(dest)
            shutil.copytree(src, dest)
            self.logger(f"copied  {src} -> {dest}")
            return

        # Regular file.
        if (
            dest.is_file()
            and not dest.is_symlink()
            and _files_identical(src, dest)
        ):
            self.logger(f"skip    {dest} (identical)")
            return
        if dest.exists() or dest.is_symlink():
            _remove(dest)
        shutil.copyfile(src, dest)
        try:
            shutil.copymode(src, dest)
        except OSError:
            pass
        self.logger(f"copied  {src} -> {dest}")

    def _insert(self, args: list[str], position: str) -> None:
        name = "PREPENDTEXT" if position == "prepend" else "APPENDTEXT"
        if len(args) < 3:
            self.logger(f"{name} needs <source> <dest> <section_id>. Skipping.")
            return
        src = self.pkg_dir / args[0]
        dest = self._dest(args[1])
        section_id = args[2]
        comment = args[3] if len(args) >= 4 and args[3] else DEFAULT_COMMENT
        if not src.is_file():
            raise SpecError(f"Source file not found: {src}")
        textutil.insert_section(
            dest=dest,
            source=src,
            section_id=section_id,
            comment=comment,
            position=position,
        )
        self.logger(f"{position}ed section '{section_id}' -> {dest}")

    def _prependtext(self, args: list[str]) -> None:
        self._insert(args, "prepend")

    def _appendtext(self, args: list[str]) -> None:
        self._insert(args, "append")

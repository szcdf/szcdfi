"""Parsing of ``.szcdfis`` manifest lines, including the shell/platform guard.

A manifest line is one of:

* ``<DIRECTIVE> <args...>``     -- shared; active for every installer.
* ``#@<guard> <DIRECTIVE> ...`` -- active ONLY when ``<guard>`` is in the
  installer's active guard set; a comment to every other installer.
* ``# ...``                     -- an ordinary comment, always ignored.
* (blank)                       -- ignored.

The guard model is what lets one manifest serve every shell and platform: a
guarded line is inert to every non-matching installer and active to the matching
one. This single engine resolves guards uniformly instead of each shell's
installer re-implementing the rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `#@<guard> <rest...>` -- guard token is the run of non-whitespace after `#@`.
_GUARD_RE = re.compile(r"^#@(\S+)\s+(.*)$")


@dataclass(frozen=True)
class Directive:
    """A single active directive: its name, its args, and the source text."""

    name: str
    args: list[str]
    text: str


def active_directive(line: str, guards: set[str]) -> str | None:
    """Return the active directive text for a manifest ``line``, or ``None``.

    ``None`` means the line is not active for this installer: it is blank, an
    ordinary comment, or guarded for a shell/platform not in ``guards``.
    """
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("#@"):
        match = _GUARD_RE.match(stripped)
        if not match:
            return None
        guard, rest = match.group(1), match.group(2)
        if guard in guards:
            return rest.strip() or None
        return None
    if stripped.startswith("#"):
        return None
    return stripped


def parse_directive(text: str) -> Directive:
    """Split an active directive line into name + args by whitespace.

    Matches the word-splitting of both reference installers (Bash's unquoted
    ``$line`` expansion and PowerShell's ``\\s+`` split): no quote handling, runs
    of whitespace collapse, empties drop.
    """
    tokens = text.split()
    if not tokens:
        return Directive(name="", args=[], text=text)
    return Directive(name=tokens[0], args=tokens[1:], text=text)


def iter_directives(lines: list[str], guards: set[str]):
    """Yield a :class:`Directive` for every active line in ``lines``."""
    for raw in lines:
        text = active_directive(raw, guards)
        if text is None:
            continue
        yield parse_directive(text)

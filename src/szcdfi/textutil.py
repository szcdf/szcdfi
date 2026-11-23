"""Correct, uniform text handling for szcdf-managed files.

This module is the single reason szcdf has one installer engine. Every rule the
Bash and PowerShell prototypes had to re-implement (and sometimes got wrong)
lives here, once:

* **UTF-8 without a BOM.** Files are written as UTF-8 and never carry a byte
  order mark. A leading BOM, for example, breaks Claude Code's ``@import``
  parsing and glues an invisible byte onto the first managed line.
* **Destination-EOL preservation.** Editing an existing file keeps that file's
  dominant line ending: a CRLF file stays CRLF, an LF file stays LF. A brand-new
  file defaults to LF (the byte style the Bash installer emitted).
* **The exact SZCDF section-marker format**, with the END marker always on its
  own line -- i.e. NOT the Bash ``cat``-gluing bug where a source file lacking a
  trailing newline would weld the END marker onto its last content line.
"""

from __future__ import annotations

import re
from pathlib import Path

# Match a line ending: CRLF first (so it is consumed as one unit), then CR, then
# LF. We deliberately do NOT use str.splitlines(), which also splits on
# vertical tab, form feed, and other Unicode separators we must leave intact.
_EOL_RE = re.compile(r"\r\n|\r|\n")

LF = "\n"
CRLF = "\r\n"

BEGIN_TEMPLATE = (
    "{comment} >>>>>>> SZCDF_GENERATED_TEXT // BEGIN SECTION_ID={section_id} "
    "// DO NOT EDIT MANUALLY"
)
END_TEMPLATE = (
    "{comment} <<<<<<< SZCDF_GENERATED_TEXT // END SECTION_ID={section_id} "
    "// DO NOT EDIT MANUALLY"
)


def detect_dominant_eol(path: Path) -> str:
    """Return the dominant EOL of an existing file.

    CRLF if the file contains any CRLF sequence, else LF. A missing or empty
    file reports LF -- the default byte style for new szcdf-managed files.
    """
    if path.is_file():
        raw = path.read_bytes()
        if b"\r\n" in raw:
            return CRLF
    return LF


def read_text_lines(path: Path) -> list[str]:
    """Read a UTF-8 text file into lines WITHOUT their terminators.

    * Decodes as UTF-8, tolerating and stripping a leading BOM if one is present
      (``utf-8-sig``). This is the fix for the "ANSI vs UTF-8 read" parity bug:
      the file is never decoded with a locale/ANSI code page.
    * A trailing newline does NOT yield a final empty element, mirroring the
      line model used when the content is written back.
    * A missing file reads as no lines.
    """
    if not path.is_file():
        return []
    text = path.read_bytes().decode("utf-8-sig")
    if text == "":
        return []
    parts = _EOL_RE.split(text)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def write_text_lines(path: Path, lines: list[str], eol: str = LF) -> None:
    """Write ``lines`` joined by ``eol`` as UTF-8 WITHOUT a BOM.

    A non-empty file ends with a single trailing ``eol``. Because the content is
    built from a list of whole lines, a marker is always on its own line -- the
    Bash gluing bug cannot occur here by construction.
    """
    content = eol.join(lines)
    if content:
        content += eol
    path.write_bytes(content.encode("utf-8"))


def section_markers(comment: str, section_id: str) -> tuple[str, str]:
    """Return the (begin, end) marker lines for a section.

    Byte-identical to the Bash and PowerShell installers, so files stay
    interoperable across every installer that ever touched them.
    """
    begin = BEGIN_TEMPLATE.format(comment=comment, section_id=section_id)
    end = END_TEMPLATE.format(comment=comment, section_id=section_id)
    return begin, end


def insert_section(
    dest: Path,
    source: Path,
    section_id: str,
    comment: str = "#",
    position: str = "prepend",
) -> None:
    """Insert (or replace) a managed section in ``dest`` from ``source``.

    If ``dest`` already contains both markers for ``section_id``, the body
    between them is replaced in place (its position in the file is kept).
    Otherwise a new section is prepended or appended per ``position``
    (``"prepend"`` or ``"append"``).

    The destination's dominant EOL is preserved; output is UTF-8 without a BOM.
    """
    if position not in ("prepend", "append"):
        raise ValueError(f"position must be 'prepend' or 'append', got {position!r}")

    begin, end = section_markers(comment, section_id)
    src_lines = read_text_lines(source)
    dest_lines = read_text_lines(dest)
    eol = detect_dominant_eol(dest)

    if begin in dest_lines and end in dest_lines:
        result: list[str] = []
        in_section = False
        for line in dest_lines:
            if line == begin:
                result.append(begin)
                result.extend(src_lines)
                in_section = True
                continue
            if in_section:
                if line == end:
                    result.append(end)
                    in_section = False
                continue
            result.append(line)
        write_text_lines(dest, result, eol)
        return

    section = [begin, *src_lines, end]
    if position == "prepend":
        result = [*section, *dest_lines]
    else:
        result = [*dest_lines, *section]
    write_text_lines(dest, result, eol)

"""Tests for the text-handling rules -- the reason szcdf has one engine.

Each parity bug the Bash/PowerShell prototypes hit (BOM, ANSI reads, CRLF
normalization, END-marker gluing) is pinned here as a regression test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from szcdfi import textutil


# --- marker format --------------------------------------------------------- #


def test_marker_format_is_exact():
    begin, end = textutil.section_markers("#", "ENTRY-BASH")
    assert begin == (
        "# >>>>>>> SZCDF_GENERATED_TEXT // BEGIN SECTION_ID=ENTRY-BASH "
        "// DO NOT EDIT MANUALLY"
    )
    assert end == (
        "# <<<<<<< SZCDF_GENERATED_TEXT // END SECTION_ID=ENTRY-BASH "
        "// DO NOT EDIT MANUALLY"
    )


def test_marker_honors_custom_comment_indicator():
    begin, end = textutil.section_markers("//", "X")
    assert begin.startswith("// >>>>>>> ")
    assert end.startswith("// <<<<<<< ")


# --- BOM-free output ------------------------------------------------------- #


def test_write_never_emits_bom(tmp_path: Path):
    dest = tmp_path / "out.txt"
    textutil.write_text_lines(dest, ["alpha", "beta"], textutil.LF)
    raw = dest.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw == b"alpha\nbeta\n"


def test_insert_strips_a_preexisting_bom(tmp_path: Path):
    dest = tmp_path / "rc"
    dest.write_bytes(b"\xef\xbb\xbfexisting\n")
    src = tmp_path / "src"
    src.write_text("managed\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", comment="#", position="prepend")
    raw = dest.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\xef\xbb\xbf" not in raw
    assert b"existing" in raw


# --- UTF-8 (not ANSI) reads ------------------------------------------------ #


def test_reads_utf8_content_without_mojibake(tmp_path: Path):
    dest = tmp_path / "rc"
    # Non-ASCII content that an ANSI/locale decode would corrupt.
    dest.write_text("café — naïve ✓\n", encoding="utf-8")
    src = tmp_path / "src"
    src.write_text("hook\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", position="prepend")
    out = dest.read_bytes().decode("utf-8")
    assert "café — naïve ✓" in out


# --- EOL preservation ------------------------------------------------------ #


def test_detect_dominant_eol(tmp_path: Path):
    lf = tmp_path / "lf"
    lf.write_bytes(b"a\nb\n")
    crlf = tmp_path / "crlf"
    crlf.write_bytes(b"a\r\nb\r\n")
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    assert textutil.detect_dominant_eol(lf) == textutil.LF
    assert textutil.detect_dominant_eol(crlf) == textutil.CRLF
    assert textutil.detect_dominant_eol(missing) == textutil.LF
    assert textutil.detect_dominant_eol(empty) == textutil.LF


def test_crlf_file_stays_crlf(tmp_path: Path):
    dest = tmp_path / "rc"
    dest.write_bytes(b"line1\r\nline2\r\n")
    src = tmp_path / "src"
    src.write_bytes(b"hookA\nhookB\n")  # LF source
    textutil.insert_section(dest, src, "ID", position="prepend")
    raw = dest.read_bytes()
    # Every line ending is CRLF; no lone LF survived.
    assert b"\r\n" in raw
    assert raw.replace(b"\r\n", b"") .count(b"\n") == 0
    assert raw.startswith(b"# >>>>>>> SZCDF_GENERATED_TEXT")
    assert b"line1\r\n" in raw and b"line2\r\n" in raw
    assert b"hookA\r\n" in raw and b"hookB\r\n" in raw


def test_new_file_defaults_to_lf(tmp_path: Path):
    dest = tmp_path / "rc"  # does not exist
    src = tmp_path / "src"
    src.write_bytes(b"hook\n")
    textutil.insert_section(dest, src, "ID", position="prepend")
    raw = dest.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


# --- END-marker gluing regression ----------------------------------------- #


def test_end_marker_on_its_own_line_even_without_trailing_newline(tmp_path: Path):
    """The Bash `cat` bug: a source with no trailing newline welded the END
    marker onto the last content line. The line model must prevent that."""
    dest = tmp_path / "rc"  # new file
    src = tmp_path / "src"
    src.write_bytes(b"no-trailing-newline")  # deliberately no \n
    textutil.insert_section(dest, src, "ID", comment="#", position="append")
    lines = dest.read_bytes().decode("utf-8").split("\n")
    begin, end = textutil.section_markers("#", "ID")
    assert begin in lines
    assert end in lines  # END is its own element, not "no-trailing-newline# <<< ..."
    assert "no-trailing-newline" in lines
    # The content line and the END marker are distinct, adjacent lines.
    assert lines.index(end) == lines.index("no-trailing-newline") + 1


# --- prepend / append / replace semantics ---------------------------------- #


def test_prepend_puts_section_at_top(tmp_path: Path):
    dest = tmp_path / "rc"
    dest.write_text("user-line\n", encoding="utf-8")
    src = tmp_path / "src"
    src.write_text("hook\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", position="prepend")
    lines = dest.read_text(encoding="utf-8").splitlines()
    begin, end = textutil.section_markers("#", "ID")
    assert lines[0] == begin
    assert lines[-1] == "user-line"


def test_append_puts_section_at_bottom(tmp_path: Path):
    dest = tmp_path / "rc"
    dest.write_text("user-line\n", encoding="utf-8")
    src = tmp_path / "src"
    src.write_text("hook\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", position="append")
    lines = dest.read_text(encoding="utf-8").splitlines()
    begin, end = textutil.section_markers("#", "ID")
    assert lines[0] == "user-line"
    assert lines[-1] == end


def test_existing_section_is_replaced_in_place(tmp_path: Path):
    dest = tmp_path / "rc"
    src = tmp_path / "src"
    src.write_text("v1\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", position="prepend")
    # Add a user line after the section, then re-run with new content.
    with dest.open("a", encoding="utf-8") as fh:
        fh.write("user-tail\n")
    src.write_text("v2-a\nv2-b\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", position="append")  # position ignored
    lines = dest.read_text(encoding="utf-8").splitlines()
    begin, end = textutil.section_markers("#", "ID")
    assert "v1" not in lines
    assert "v2-a" in lines and "v2-b" in lines
    assert "user-tail" in lines
    # Section body replaced between the markers; markers appear exactly once.
    assert lines.count(begin) == 1 and lines.count(end) == 1
    # user-tail stayed after the section (section kept its position).
    assert lines.index("user-tail") > lines.index(end)


def test_idempotent_rerun_leaves_file_byte_identical(tmp_path: Path):
    dest = tmp_path / "rc"
    dest.write_text("user-line\n", encoding="utf-8")
    src = tmp_path / "src"
    src.write_text("hook\n", encoding="utf-8")
    textutil.insert_section(dest, src, "ID", position="prepend")
    first = dest.read_bytes()
    textutil.insert_section(dest, src, "ID", position="prepend")
    assert dest.read_bytes() == first


def test_read_text_lines_drops_only_final_empty(tmp_path: Path):
    p = tmp_path / "f"
    p.write_bytes(b"a\nb\n")
    assert textutil.read_text_lines(p) == ["a", "b"]
    p.write_bytes(b"a\nb")
    assert textutil.read_text_lines(p) == ["a", "b"]
    p.write_bytes(b"a\n\nb\n")
    assert textutil.read_text_lines(p) == ["a", "", "b"]
    assert textutil.read_text_lines(tmp_path / "missing") == []

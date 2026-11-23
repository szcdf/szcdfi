"""Tests for the manifest parser and the shell/platform guard model."""

from __future__ import annotations

from szcdfi import manifest


def test_shared_directive_is_active_for_any_guards():
    assert manifest.active_directive("COPY a b", set()) == "COPY a b"
    assert manifest.active_directive("COPY a b", {"bash"}) == "COPY a b"


def test_blank_and_ordinary_comment_are_inactive():
    assert manifest.active_directive("", {"bash"}) is None
    assert manifest.active_directive("   ", {"bash"}) is None
    assert manifest.active_directive("# just a comment", {"bash"}) is None
    assert manifest.active_directive("#still a comment", {"bash"}) is None


def test_guard_active_only_for_matching_shell():
    line = "#@pwsh PREPENDTEXT src/entry.ps1 $PROFILE ENTRY-PWSH"
    assert manifest.active_directive(line, {"pwsh"}) == (
        "PREPENDTEXT src/entry.ps1 $PROFILE ENTRY-PWSH"
    )
    # A comment to every non-matching installer.
    assert manifest.active_directive(line, {"bash"}) is None
    assert manifest.active_directive(line, set()) is None


def test_bash_guard_ignored_by_pwsh_and_vice_versa():
    bash_line = "#@bash PREPENDTEXT src/entry.sh $HOME/.bashrc ENTRY-BASH"
    assert manifest.active_directive(bash_line, {"bash"}).startswith("PREPENDTEXT")
    assert manifest.active_directive(bash_line, {"pwsh"}) is None


def test_guard_with_leading_whitespace_is_still_parsed():
    assert manifest.active_directive("   #@bash COPY a b", {"bash"}) == "COPY a b"


def test_malformed_guard_without_directive_is_inactive():
    # `#@bash` with nothing after it is not a directive.
    assert manifest.active_directive("#@bash", {"bash"}) is None
    assert manifest.active_directive("#@bash   ", {"bash"}) is None


def test_parse_directive_splits_name_and_args():
    d = manifest.parse_directive("COPY bin/x.sh $HOME/.local/bin/x.sh")
    assert d.name == "COPY"
    assert d.args == ["bin/x.sh", "$HOME/.local/bin/x.sh"]


def test_parse_directive_collapses_runs_of_whitespace():
    d = manifest.parse_directive("COPYALL   src/mods    $CONFIG_ROOT/modules")
    assert d.name == "COPYALL"
    assert d.args == ["src/mods", "$CONFIG_ROOT/modules"]


def test_iter_directives_filters_the_whole_manifest():
    lines = [
        "# header comment",
        "",
        "COPY a b",
        "#@pwsh COPY win c",
        "#@bash PREPENDTEXT s d ID",
        "COPYALL e f",
    ]
    bash = list(manifest.iter_directives(lines, {"bash"}))
    assert [d.name for d in bash] == ["COPY", "PREPENDTEXT", "COPYALL"]

    pwsh = list(manifest.iter_directives(lines, {"pwsh"}))
    assert [d.name for d in pwsh] == ["COPY", "COPY", "COPYALL"]
    assert pwsh[1].args == ["win", "c"]

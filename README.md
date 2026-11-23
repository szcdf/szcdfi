# szcdfi

The cross-platform installer for the szcdf dotfiles framework.

`szcdfi` reads a `.szcdfis` manifest. It provisions files into your config root.
It is one engine for every shell and every platform.

- It is a standalone Python package.
- It uses only the Python standard library. It has no third-party run-time
  dependencies.
- You run it with `uv`. `uv` supplies a managed Python. You do not need a system
  Python.

See ADR-0003 for the decision behind this design.

## Prerequisite: uv

You need `uv`. Install it one time.

- On Windows:

  ```powershell
  winget install astral-sh.uv
  ```

- On macOS or Linux:

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## How to run szcdfi

Go to your szcdf package directory first. The package directory holds the
`.szcdfis` manifest.

- To run the latest version one time:

  ```sh
  uvx szcdfi@latest
  ```

- To install a persistent command:

  ```sh
  uv tool install szcdfi
  szcdfi
  ```

The installer does these steps:

1. It finds your config root.
2. It reads the manifest.
3. It shows you the planned changes.
4. It asks you to continue. (Use `-I` to skip the question.)
5. It applies the changes.

## Options

| Option | Effect |
| --- | --- |
| `-p`, `--package-dir <dir>` | Set the package directory. The default is the current directory, searched upward for a `.szcdfis`. |
| `-s`, `--spec <file>` | Set the manifest file. |
| `-m`, `--mode quick\|custom` | `quick` confirms once. `custom` confirms each step. The default is `quick`. |
| `-I`, `--non-interactive` | Apply without a question. Use this for scripts and CI. |
| `-e`, `--editable` | Make symbolic links instead of copies. Use this for development. |
| `-g`, `--guard <id>` | Set a guard token. Repeat the option for more than one. This overrides the platform default. |
| `-n`, `--dry-run` | Show the plan only. Change nothing. |
| `-V`, `--version` | Show the version. |

## The config root

The installer writes into one config root. It finds the root in this order:

- Use `~/.config/szcdf` if that directory exists.
- Else use `~/.szcdf` if that directory exists.
- Else create `~/.config/szcdf` and use it.

In a manifest, `$CONFIG_ROOT` means this root. `$HOME` means your home
directory.

## The manifest: `.szcdfis`

A manifest is a list of lines. Each line is a directive, a guarded directive, or
a comment.

### Directives

- `COPY <source> <dest>`
  - It copies one file or one directory.
  - `<source>` is relative to the package directory.
  - `<dest>` can use `$CONFIG_ROOT` and `$HOME`.
- `COPYALL <source_dir> <dest_dir>`
  - It copies each direct child of `<source_dir>` into `<dest_dir>`.
  - It is not recursive at the top level. A child directory copies as a unit.
- `PREPENDTEXT <source> <dest> <section_id> [comment]`
  - It adds a managed section to the top of `<dest>`.
  - `<source>` supplies the section body.
  - `[comment]` is the comment marker. The default is `#`.
- `APPENDTEXT <source> <dest> <section_id> [comment]`
  - It adds a managed section to the end of `<dest>`.
  - The arguments match `PREPENDTEXT`.

A managed section has two markers:

```text
# >>>>>>> SZCDF_GENERATED_TEXT // BEGIN SECTION_ID=<id> // DO NOT EDIT MANUALLY
...your section body...
# <<<<<<< SZCDF_GENERATED_TEXT // END SECTION_ID=<id> // DO NOT EDIT MANUALLY
```

A re-run updates the body between the markers. It keeps the section in place. It
does not add a second copy.

### The guard model

One manifest serves every shell and every platform. A guard controls this.

- A line with no guard is shared. Every installer applies it.
- A line `#@<guard> <directive> ...` is guarded.
  - The installer applies it only when `<guard>` is in the active guard set.
  - To every other installer, the line is a comment.
- A line `# ...` is an ordinary comment. Every installer ignores it.

The active guard set has a default. The default depends on the platform.

- On Windows: `pwsh`, `powershell`, `windows`, `nt`, `win`.
- On macOS: `bash`, `sh`, `zsh`, `posix`, `unix`, `darwin`, `macos`, `mac`,
  `osx`.
- On Linux: `bash`, `sh`, `zsh`, `posix`, `unix`, `linux`.

Use `--guard` to set the active guard set yourself.

Example:

```text
COPYALL src/core-modules $CONFIG_ROOT/modules
#@bash PREPENDTEXT src/entry-bash.sh $HOME/.bashrc ENTRY-BASH
#@pwsh PREPENDTEXT src/entry-pwsh.ps1 $PROFILE ENTRY-PWSH
```

## Text handling

The installer writes text with strict rules. The rules keep managed files
correct on every platform.

- It writes UTF-8. It never writes a byte order mark (BOM).
- It keeps the line ending of the destination file.
  - A CRLF file stays CRLF.
  - A LF file stays LF.
  - A new file uses LF.
- It puts each marker on its own line.

## Development

Run the tests with `uv`:

```sh
uv run --group dev pytest
```

The tests cover the directive engine, the guard parser, and the text-handling
rules. They include regression tests for known parity bugs: a BOM, an ANSI read,
CRLF normalization, and a glued END marker.

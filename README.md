# Codex Long-Term Memory Bundle

This repository is a sanitized transplant bundle for a Codex long-term-memory setup.
It is not a standalone application and it does not publish any live memory data.

The packaged runtime stores per-project memory, regenerates a lightweight `MEMORY.md`
front page, and exposes manual recall through a CLI. Codex can also call the runtime
automatically through its `notify` hook.

## Current Status

- Packaged here: the global Codex memory bundle that installs into `~/.codex`.
- Storage model: per-project SQLite databases under `~/.codex/projects/<project-id>/`.
- Automatic Codex persistence: supported through the `notify` command in the config snippet.
- Manual recall from any agent: supported by running the CLI search command.
- Claude Code automatic hooks: not included in this repository.

Claude Code can use the same memories when it is instructed to run the CLI, but this
bundle alone does not install Claude Code `UserPromptSubmit` or `Stop` hooks. Automatic
Codex + Claude Code shared hooks require the newer project-local runtime shape:
`.project-memory/`, `.claude/settings.json`, and a host-aware hook bridge.

## What Is Included

- `bin/codex_memory.py`
- `memory-runtime/.python-version`
- `memory-runtime/pyproject.toml`
- `memory-runtime/uv.lock`
- `snippets/AGENTS.md`
- `snippets/config.toml.long-term-memory.toml`

## What Is Not Included

- `projects/*/memory.db`
- `sessions/*.jsonl`
- `log/*`
- generated `MEMORY.md`
- Claude Code project hook settings
- unrelated Codex settings and MCP servers
- host-specific secrets, tokens, or credentials

## Target Layout

Merge the files into this layout on the target host:

```text
~/.codex/
  AGENTS.md
  config.toml
  bin/
    codex_memory.py
  memory-runtime/
    .python-version
    pyproject.toml
    uv.lock
```

## Install On Another Host

1. Copy `bin/codex_memory.py` to `~/.codex/bin/codex_memory.py`.
2. Copy `memory-runtime/` into `~/.codex/memory-runtime/`.
3. Merge `snippets/config.toml.long-term-memory.toml` into `~/.codex/config.toml`.
4. Merge the long-term-memory section from `snippets/AGENTS.md` into `~/.codex/AGENTS.md`.
5. Run `cd ~/.codex/memory-runtime && uv sync`.
6. In a target repo, initialize memory once:

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" init --cwd "$PWD"
```

## How To Use

Use this bundle as a lightweight project memory layer for Codex:

1. Install the bundle into `~/.codex` and merge the config snippet.
2. Open the repository you want Codex to remember.
3. Run `init --cwd "$PWD"` once in that repository.
4. Work normally in Codex. The `notify` hook records useful turn context after each session.
5. When a task depends on previous decisions, debugging dead ends, migration plans, or
   continuity signals such as "previous", "continue", or "why did we reject this", run
   `search --cwd "$PWD" --query "<topic>"` before acting.
6. Use the generated `MEMORY.md` only as a front page. SQLite remains the source of truth.

For Claude Code or another coding agent, use the same CLI command for manual recall:

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" search --cwd "$PWD" --query "<topic>"
```

This repository does not install automatic Claude Code hooks. It only provides the shared
memory runtime and CLI that another agent can call.

## Daily Commands

Search memory for the current repository:

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" search --cwd "$PWD" --query "<topic>"
```

Regenerate the local `MEMORY.md` front page:

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" refresh --cwd "$PWD"
```

Backfill memories from saved Codex session logs:

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" sync --cwd "$PWD"
```

## Behavior

- The source of truth is SQLite, not `MEMORY.md`.
- `MEMORY.md` is a generated front page for quick orientation.
- Current code and current user instructions always override recalled memory.
- The CLI redacts common secret patterns before storing turns.
- Embeddings are optional and disabled unless `CODEX_MEMORY_ENABLE_EMBEDDINGS=1` is set.
- Without embeddings, search still works through SQLite FTS/trigram search.

## Claude Code Notes

There are two useful integration levels:

1. Manual recall: Claude Code can run the same CLI command shown above. This is available
   with the files in this repository.
2. Automatic recall and persistence: requires project-local Claude Code hooks. Those files
   are not part of this sanitized bundle.

For automatic Claude Code integration, publish a separate project-local bundle that includes
sanitized versions of:

- `.project-memory/run-memory.sh`
- `.project-memory/project_memory_runtime.py`
- `.project-memory/project_memory_hook.py`
- `.project-memory/bootstrap.sh`
- `.project-memory/requirements.txt`
- `.project-memory/codex-hooks.json.template`
- `.project-memory/codex-config.toml.template`
- `.project-memory/install-codex-config.sh`
- `.claude/settings.json` or a path-neutral template
- `CLAUDE.md`
- `AGENTS.md`

Do not publish project state directories, live databases, runtime logs, spool files, or
generated `MEMORY.md` files.

## Validation

The GitHub Actions workflow parses the Python entrypoint:

```bash
python -m py_compile bin/codex_memory.py
```

Run the same command locally before pushing changes to this bundle.

## Publishing

This repository is sanitized for GitHub publication. Before publishing, review
[PUBLISHING.md](PUBLISHING.md), check [MANIFEST.md](MANIFEST.md), and choose a license
if you want third parties to reuse the code.

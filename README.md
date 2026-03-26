# Codex Long-Term Memory Bundle

This repository contains the minimum file set needed to reuse a Codex long-term-memory setup on another machine.

It is a transplant bundle, not a standalone app.
You merge these files into an existing `~/.codex` installation.

It does not include live databases, session history, logs, or generated `MEMORY.md` files.

## What is included

- `bin/codex_memory.py`
- `memory-runtime/.python-version`
- `memory-runtime/pyproject.toml`
- `memory-runtime/uv.lock`
- `snippets/AGENTS.md`
- `snippets/config.toml.long-term-memory.toml`

## What is not included

- `projects/*/memory.db`
- `sessions/*.jsonl`
- `log/*`
- generated `MEMORY.md`
- unrelated Codex settings and MCP servers

## Target layout

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

## Install on another host

1. Copy `bin/codex_memory.py` to `~/.codex/bin/codex_memory.py`.
2. Copy `memory-runtime/` into `~/.codex/memory-runtime/`.
3. Merge `snippets/config.toml.long-term-memory.toml` into `~/.codex/config.toml`.
4. Merge the long-term-memory section from `snippets/AGENTS.md` into `~/.codex/AGENTS.md`.
5. Run `cd ~/.codex/memory-runtime && uv sync`.
6. In a target repo, run `"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" init --cwd "$PWD"` once.

## Behavior

- Memory is stored per project under `~/.codex/projects/<project-id>/memory.db`.
- `MEMORY.md` is generated later by `init`, `refresh`, or a successful `notify`.
- Search uses `codex_memory.py search --cwd "$PWD" --query "<topic>"`.

## Publishing

This repository is sanitized for GitHub publication.
Before publishing, review [PUBLISHING.md](PUBLISHING.md) and choose a license if you want third parties to reuse the code.

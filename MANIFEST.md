# Bundle Manifest

This repository contains only the files needed to transplant the global Codex long-term-memory setup into another `~/.codex` installation.

Included:

- `bin/codex_memory.py`
- `memory-runtime/.python-version`
- `memory-runtime/pyproject.toml`
- `memory-runtime/uv.lock`
- `snippets/AGENTS.md`
- `snippets/config.toml.long-term-memory.toml`

Excluded on purpose:

- live `memory.db` files
- saved session logs
- generated `MEMORY.md` files
- Claude Code project hook settings
- unrelated Codex settings
- host-specific secrets

Repository-only helper files:

- `README.md`
- `README-JA.md`
- `MANIFEST.md`
- `PUBLISHING.md`
- `.gitignore`
- `.github/workflows/validate.yml`

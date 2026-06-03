# Publishing Notes

This repository is prepared for public GitHub publication.

## Before you publish

1. Review `README.md` for wording and repository name.
2. Review `README-JA.md` if you want to keep the Japanese documentation in sync.
3. Decide whether to add a `LICENSE` file.
4. Confirm `snippets/config.toml.long-term-memory.toml` matches the target Codex version you want to support.
5. Confirm `bin/codex_memory.py` contains no organization-specific behavior.
6. Confirm the README does not claim Claude Code automatic hooks are included unless the project-local hook runtime is also published.

## Suggested repository name

- `codex-long-term-memory-bundle`

## Suggested publish flow

```bash
cd portable-bundle
git add .
git commit -m "Initial import"
git remote add origin git@github.com:<you>/codex-long-term-memory-bundle.git
git push -u origin main
```

## What this repository intentionally does not publish

- current host session history
- current host memory databases
- current host logs
- generated `MEMORY.md`
- Claude Code `.claude/settings.json` files with absolute local paths
- project-local runtime state such as `runtime/` and `spool/`

## Validation

GitHub Actions in `.github/workflows/validate.yml` checks that the copied Python entrypoint parses successfully on Python 3.12.

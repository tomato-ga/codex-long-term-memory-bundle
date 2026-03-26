# Publishing Notes

This repository is prepared for public GitHub publication.

## Before you publish

1. Review `README.md` for wording and repository name.
2. Decide whether to add a `LICENSE` file.
3. Confirm `snippets/config.toml.long-term-memory.toml` matches the target Codex version you want to support.
4. Confirm `bin/codex_memory.py` contains no organization-specific behavior.

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

## Validation

GitHub Actions in `.github/workflows/validate.yml` checks that the copied Python entrypoint parses successfully on Python 3.12.

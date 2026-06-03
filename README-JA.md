# Codex Long-Term Memory Bundle

このリポジトリは、Codex 用の長期記憶セットアップを別マシンへ移植するための
サニタイズ済み bundle です。単体アプリではなく、ライブ記憶データも含みません。

同梱 runtime は、プロジェクトごとの記憶を SQLite に保存し、軽量な `MEMORY.md`
front page を再生成し、CLI で手動 recall できるようにします。Codex では
`notify` hook から自動保存もできます。

## 現在の状態

- この repo に含まれるもの: `~/.codex` へ入れるグローバル Codex memory bundle
- 保存先: `~/.codex/projects/<project-id>/` 配下の project 別 SQLite
- Codex の自動保存: config snippet の `notify` で対応
- 任意 agent からの手動 recall: CLI search で対応
- Claude Code の自動 hook: この repo には未同梱

Claude Code でも、この CLI を実行するよう指示すれば同じ記憶を参照できます。
ただし、この bundle だけでは Claude Code の `UserPromptSubmit` / `Stop` hooks は
入りません。Codex + Claude Code の自動共有 hook には、新しい project-local runtime
構成、つまり `.project-memory/`、`.claude/settings.json`、host-aware hook bridge が
必要です。

## 含まれるもの

- `bin/codex_memory.py`
- `memory-runtime/.python-version`
- `memory-runtime/pyproject.toml`
- `memory-runtime/uv.lock`
- `snippets/AGENTS.md`
- `snippets/config.toml.long-term-memory.toml`

## 含まれないもの

- `projects/*/memory.db`
- `sessions/*.jsonl`
- `log/*`
- 生成済み `MEMORY.md`
- Claude Code 用 project hook 設定
- 無関係な Codex 設定や MCP server
- host 固有の secret、token、credential

## インストール先レイアウト

移植先では、次のように `~/.codex` へマージします。

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

## 別ホストへのインストール

1. `bin/codex_memory.py` を `~/.codex/bin/codex_memory.py` へコピーする。
2. `memory-runtime/` を `~/.codex/memory-runtime/` へコピーする。
3. `snippets/config.toml.long-term-memory.toml` を `~/.codex/config.toml` へマージする。
4. `snippets/AGENTS.md` の長期記憶セクションを `~/.codex/AGENTS.md` へマージする。
5. `cd ~/.codex/memory-runtime && uv sync` を実行する。
6. 対象 repo で一度だけ初期化する。

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" init --cwd "$PWD"
```

## How To Use

この bundle は、Codex の軽量な project memory layer として使います。

1. bundle を `~/.codex` に入れ、config snippet をマージする。
2. Codex に記憶させたいリポジトリを開く。
3. そのリポジトリで一度だけ `init --cwd "$PWD"` を実行する。
4. Codex で通常どおり作業する。`notify` hook がセッション後に有用な turn context を保存する。
5. 以前の設計判断、debugging dead end、migration plan、または「前回」「続き」「なぜ却下したか」
   のような継続性シグナルがあるときは、作業前に `search --cwd "$PWD" --query "<topic>"` を実行する。
6. 生成される `MEMORY.md` は front page としてだけ使う。source of truth は SQLite。

Claude Code や他の coding agent からは、同じ CLI を手動 recall として使えます。

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" search --cwd "$PWD" --query "<topic>"
```

この repository は Claude Code の自動 hook はインストールしません。
共有 memory runtime と CLI を提供し、他 agent が必要に応じて呼び出せる形にしています。

## 日常コマンド

現在の repo の記憶を検索します。

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" search --cwd "$PWD" --query "<topic>"
```

`MEMORY.md` front page を再生成します。

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" refresh --cwd "$PWD"
```

保存済み Codex session log から記憶を backfill します。

```bash
"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" sync --cwd "$PWD"
```

## 挙動

- source of truth は SQLite であり、`MEMORY.md` ではありません。
- `MEMORY.md` はセッション復帰用の自動生成 front page です。
- 現在のコードと現在のユーザー指示は、recall された記憶より常に優先です。
- 保存前に一般的な secret pattern は redaction されます。
- embedding は任意で、`CODEX_MEMORY_ENABLE_EMBEDDINGS=1` のときだけ有効です。
- embedding なしでも SQLite FTS/trigram search で検索できます。

## Claude Code について

利用レベルは2つに分かれます。

1. 手動 recall: Claude Code が上記 CLI を実行すれば利用可能。この repo のファイルで対応できます。
2. 自動 recall / persistence: Claude Code の project-local hooks が必要。この repo には未同梱です。

Claude Code 自動連携を公開する場合は、次のようなファイルを path-neutral に
サニタイズして別 bundle として含めます。

- `.project-memory/run-memory.sh`
- `.project-memory/project_memory_runtime.py`
- `.project-memory/project_memory_hook.py`
- `.project-memory/bootstrap.sh`
- `.project-memory/requirements.txt`
- `.project-memory/codex-hooks.json.template`
- `.project-memory/codex-config.toml.template`
- `.project-memory/install-codex-config.sh`
- `.claude/settings.json` または path-neutral template
- `CLAUDE.md`
- `AGENTS.md`

project state directory、ライブ DB、runtime log、spool file、生成済み `MEMORY.md` は
公開しません。

## 検証

GitHub Actions は Python entrypoint の parse を確認します。

```bash
python -m py_compile bin/codex_memory.py
```

push 前にローカルでも同じコマンドを実行してください。

## 公開前チェック

この repo は GitHub 公開用にサニタイズされています。公開前に
[PUBLISHING.md](PUBLISHING.md) と [MANIFEST.md](MANIFEST.md) を確認し、第三者利用を
想定するなら license を選んでください。

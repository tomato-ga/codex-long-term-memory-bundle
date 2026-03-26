#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import sys
import textwrap
from pathlib import Path
from typing import Sequence

try:
    import sqlite_vec
except Exception as exc:
    sqlite_vec = None
    SQLITE_VEC_IMPORT_ERROR = exc
else:
    SQLITE_VEC_IMPORT_ERROR = None

MODEL_NAME = os.environ.get("CODEX_MEMORY_MODEL", "cl-nagoya/ruri-v3-310m")
EMBEDDINGS_ENABLED = os.environ.get("CODEX_MEMORY_ENABLE_EMBEDDINGS", "").strip().lower() in {"1", "true", "yes", "on"}
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
PROJECTS_HOME = CODEX_HOME / "projects"
SESSIONS_HOME = CODEX_HOME / "sessions"

RRF_K = 60.0
HALF_LIFE_DAYS = 30.0
RECENT_LIMIT = 12
SEARCH_LIMIT_DEFAULT = 8
EMBED_BATCH_SIZE = 32

SECRET_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9._-]{20,}\.[A-Za-z0-9._-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL),
]

_EMBEDDER = None
_EMBEDDER_ERROR: Exception | None = None


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def parse_iso(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def short(text: str, width: int = 220) -> str:
    return textwrap.shorten(re.sub(r"\s+", " ", text.strip()), width=width, placeholder=" …")


def redact(text: str) -> str:
    s = text or ""
    for pat in SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    s = s.strip()
    if len(s) > 20000:
        s = s[:20000] + "\n...[truncated]..."
    return s


def serialize_f32(vector: Sequence[float]) -> bytes:
    return struct.pack("%sf" % len(vector), *vector)


def append_log(message: str, *, cwd: Path | None = None) -> None:
    line = f"[{iso_now()}] {message}\n"
    candidates = [CODEX_HOME / "log" / "codex-memory.log"]
    if cwd is not None:
        candidates.append(project_state_dir(cwd) / "notify.log")

    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:
            pass


def find_project_root(cwd: Path) -> Path:
    current = cwd.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def project_key(cwd: Path) -> str:
    root = str(find_project_root(cwd))
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:12]


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower()
    return slug or "project"


def project_state_dir(cwd: Path) -> Path:
    root = find_project_root(cwd)
    dirname = f"{slugify(root.name)}--{project_key(cwd)}"
    path = PROJECTS_HOME / dirname
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(cwd: Path) -> Path:
    return project_state_dir(cwd) / "memory.db"


def extract_message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    if not parts:
        return ""
    return parts[-1]


def ensure_embedder():
    global _EMBEDDER, _EMBEDDER_ERROR
    if not EMBEDDINGS_ENABLED:
        raise RuntimeError("embeddings disabled; set CODEX_MEMORY_ENABLE_EMBEDDINGS=1 to enable")
    if _EMBEDDER_ERROR is not None:
        raise RuntimeError(f"embedder unavailable: {_EMBEDDER_ERROR}")
    if _EMBEDDER is None:
        try:
            from sentence_transformers import SentenceTransformer

            cache = CODEX_HOME / "memory-runtime" / ".cache"
            cache.mkdir(parents=True, exist_ok=True)
            _EMBEDDER = SentenceTransformer(
                MODEL_NAME,
                cache_folder=str(cache),
                trust_remote_code=True,
            )
        except Exception as exc:
            _EMBEDDER_ERROR = exc
            append_log(f"embedder initialization failed: {exc}")
            raise
    return _EMBEDDER


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    model = ensure_embedder()
    arr = model.encode(
        list(texts),
        normalize_embeddings=True,
        batch_size=EMBED_BATCH_SIZE,
        show_progress_bar=False,
    )
    return [list(map(float, row)) for row in arr]


def embedding_dim() -> int:
    return len(embed_texts(["dimension probe"])[0])


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'virtual table') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def connect(cwd: Path) -> sqlite3.Connection:
    path = db_path(cwd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    if sqlite_vec is None:
        raise RuntimeError(
            f"sqlite-vec import failed: {SQLITE_VEC_IMPORT_ERROR}. "
            "Run uv sync in ~/.codex/memory-runtime first."
        )

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    init_schema(conn, cwd)
    return conn


def init_schema(conn: sqlite3.Connection, cwd: Path) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_key TEXT NOT NULL UNIQUE,
            thread_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            project_root TEXT NOT NULL,
            cwd TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            qa TEXT NOT NULL,
            embedded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    if not table_exists(conn, "memories_fts"):
        conn.execute(
            """
            CREATE VIRTUAL TABLE memories_fts
            USING fts5(
                qa,
                tokenize='trigram'
            )
            """
        )

    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('project_root', ?)",
        (str(find_project_root(cwd)),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('model_name', ?)",
        (MODEL_NAME,),
    )
    conn.commit()


def ensure_vector_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'embedding_dim'").fetchone()
    if row is None:
        dim = embedding_dim()
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('embedding_dim', ?)",
            (str(dim),),
        )
        conn.commit()
    else:
        dim = int(row["value"])

    if not table_exists(conn, "memories_vec"):
        conn.execute(f"CREATE VIRTUAL TABLE memories_vec USING vec0(embedding float[{dim}])")
        conn.commit()


def store_memory(
    conn: sqlite3.Connection,
    *,
    cwd: Path,
    thread_id: str,
    turn_id: str,
    question: str,
    answer: str,
) -> bool:
    question = redact(question)
    answer = redact(answer)
    if not question or not answer:
        return False

    turn_key = make_turn_key(thread_id, turn_id, question, answer)
    qa = f"Q:\n{question}\n\nA:\n{answer}"
    now = iso_now()

    existing = conn.execute(
        "SELECT id FROM memories WHERE turn_key = ?",
        (turn_key,),
    ).fetchone()
    if existing is not None:
        return False

    cur = conn.execute(
        """
        INSERT INTO memories (
            turn_key, thread_id, turn_id, project_root, cwd,
            question, answer, qa, embedded, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            turn_key,
            thread_id,
            turn_id,
            str(find_project_root(cwd)),
            str(cwd),
            question,
            answer,
            qa,
            now,
            now,
        ),
    )
    memory_id = cur.lastrowid
    conn.execute(
        "INSERT INTO memories_fts(rowid, qa) VALUES (?, ?)",
        (memory_id, qa),
    )
    conn.commit()
    return True


def iter_session_files() -> list[Path]:
    if not SESSIONS_HOME.exists():
        return []
    return sorted(SESSIONS_HOME.rglob("*.jsonl"))


def sync_session_logs(conn: sqlite3.Connection, cwd: Path) -> int:
    target_root = find_project_root(cwd)
    inserted = 0

    for session_file in iter_session_files():
        try:
            session_id = ""
            session_root: Path | None = None
            active_turn_id = ""
            questions: dict[str, str] = {}

            with session_file.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue

                    record = json.loads(line)
                    record_type = record.get("type")
                    payload = record.get("payload") or {}

                    if record_type == "session_meta":
                        session_id = str(payload.get("id") or "")
                        session_cwd = payload.get("cwd")
                        if not session_cwd:
                            break
                        session_root = find_project_root(Path(session_cwd).resolve())
                        if session_root != target_root:
                            break
                        continue

                    if session_root != target_root:
                        continue

                    if record_type == "turn_context":
                        active_turn_id = str(payload.get("turn_id") or active_turn_id)
                        continue

                    if record_type == "response_item":
                        if payload.get("type") == "message" and payload.get("role") == "user" and active_turn_id:
                            question = extract_message_text(payload.get("content"))
                            if question and active_turn_id not in questions:
                                questions[active_turn_id] = question
                        continue

                    if record_type != "event_msg":
                        continue

                    event_type = payload.get("type")
                    if event_type == "task_started":
                        active_turn_id = str(payload.get("turn_id") or active_turn_id)
                        continue

                    if event_type == "user_message" and active_turn_id:
                        question = str(payload.get("message") or "").strip()
                        if question:
                            questions[active_turn_id] = question
                        continue

                    if event_type != "task_complete":
                        continue

                    turn_id = str(payload.get("turn_id") or active_turn_id)
                    answer = str(payload.get("last_agent_message") or "").strip()
                    question = questions.get(turn_id, "")
                    if not turn_id or not question or not answer:
                        continue

                    if store_memory(
                        conn,
                        cwd=target_root,
                        thread_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        answer=answer,
                    ):
                        inserted += 1
        except Exception as exc:
            append_log(f"session sync skipped file={session_file} error={exc}", cwd=cwd)

    if inserted:
        append_log(f"session sync inserted={inserted}", cwd=cwd)
    return inserted


def make_turn_key(thread_id: str, turn_id: str, question: str, answer: str) -> str:
    raw = "\n".join([thread_id, turn_id, question, answer]).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def build_fts_query(query: str) -> str:
    safe_parts: list[str] = []
    for part in re.split(r"\s+", query.strip()):
        if not part:
            continue
        escaped = part.replace('"', '""')
        safe_parts.append(f'"{escaped}"')
        if len(safe_parts) >= 8:
            break
    return " OR ".join(safe_parts)


def age_decay(created_at: str, half_life_days: float = HALF_LIFE_DAYS) -> float:
    age_seconds = max((utcnow() - parse_iso(created_at)).total_seconds(), 0.0)
    age_days = age_seconds / 86400.0
    return math.pow(0.5, age_days / half_life_days)


def row_to_memory(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "project_root": row["project_root"],
        "cwd": row["cwd"],
        "question": row["question"],
        "answer": row["answer"],
        "qa": row["qa"],
        "created_at": row["created_at"],
    }


def backfill_embeddings(conn: sqlite3.Connection, limit: int | None = None) -> int:
    if not EMBEDDINGS_ENABLED:
        return 0
    try:
        ensure_vector_schema(conn)
    except Exception as exc:
        append_log(f"embedding backfill skipped during schema setup: {exc}")
        return 0
    total = 0
    while True:
        sql = """
            SELECT id, qa
            FROM memories
            WHERE embedded = 0
            ORDER BY id ASC
        """
        params: list[object] = []
        if limit is not None:
            remaining = limit - total
            if remaining <= 0:
                break
            sql += " LIMIT ?"
            params.append(remaining)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            break

        try:
            vectors = embed_texts([row["qa"] for row in rows])
        except Exception as exc:
            append_log(f"embedding backfill skipped during encode: {exc}")
            break
        now = iso_now()

        for row, vector in zip(rows, vectors):
            conn.execute(
                "INSERT OR REPLACE INTO memories_vec(rowid, embedding) VALUES (?, ?)",
                (row["id"], serialize_f32(vector)),
            )
            conn.execute(
                "UPDATE memories SET embedded = 1, updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )

        conn.commit()
        total += len(rows)

        if limit is not None and total >= limit:
            break

    return total


def recent_memories(conn: sqlite3.Connection, limit: int = RECENT_LIMIT) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, project_root, cwd, question, answer, qa, created_at
        FROM memories
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row_to_memory(r) | {"score": 1.0} for r in rows]


def hybrid_search(conn: sqlite3.Connection, query: str, limit: int = SEARCH_LIMIT_DEFAULT) -> list[dict]:
    query = query.strip()
    if not query:
        return recent_memories(conn, limit=limit)

    backfill_embeddings(conn)

    fts_rows = []
    fts_query = build_fts_query(query)
    if fts_query:
        fts_rows = conn.execute(
            """
            SELECT
                m.id, m.project_root, m.cwd, m.question, m.answer, m.qa, m.created_at,
                bm25(memories_fts) AS rank_score
            FROM memories_fts
            JOIN memories m ON m.id = memories_fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY rank_score ASC, m.id DESC
            LIMIT ?
            """,
            (fts_query, limit * 4),
        ).fetchall()

    vec_rows = []
    if EMBEDDINGS_ENABLED and table_exists(conn, "memories_vec"):
        try:
            query_vec = serialize_f32(embed_texts([query])[0])
            vec_rows = conn.execute(
                """
                SELECT
                    m.id, m.project_root, m.cwd, m.question, m.answer, m.qa, m.created_at,
                    memories_vec.distance AS distance
                FROM memories_vec
                JOIN memories m ON m.id = memories_vec.rowid
                WHERE embedding MATCH ?
                ORDER BY distance ASC
                LIMIT ?
                """,
                (query_vec, limit * 4),
            ).fetchall()
        except Exception as exc:
            append_log(f"vector search skipped: {exc}")

    row_cache: dict[int, dict] = {}
    fts_rank: dict[int, int] = {}
    vec_rank: dict[int, int] = {}

    for rank, row in enumerate(fts_rows, start=1):
        fts_rank[row["id"]] = rank
        row_cache[row["id"]] = row_to_memory(row)

    for rank, row in enumerate(vec_rows, start=1):
        vec_rank[row["id"]] = rank
        row_cache[row["id"]] = row_to_memory(row)

    scored = []
    for memory_id in set(fts_rank) | set(vec_rank):
        score = 0.0
        if memory_id in fts_rank:
            score += 1.0 / (RRF_K + fts_rank[memory_id])
        if memory_id in vec_rank:
            score += 1.0 / (RRF_K + vec_rank[memory_id])

        row = row_cache[memory_id]
        score *= age_decay(row["created_at"])
        scored.append(row | {"score": score})

    scored.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
    return scored[:limit]


def render_memory_md(conn: sqlite3.Connection, cwd: Path) -> str:
    root = find_project_root(cwd)
    recent = recent_memories(conn)

    lines: list[str] = []
    lines.append("# MEMORY.md")
    lines.append("")
    lines.append("> AUTOGENERATED. Do not edit by hand.")
    lines.append("> This file is the project front page for long-term memory.")
    lines.append("")
    lines.append(f"- project_root: `{root}`")
    lines.append(f"- project_state_dir: `{project_state_dir(cwd)}`")
    lines.append(f"- database: `{db_path(cwd)}`")
    lines.append(f"- generated_at_utc: `{iso_now()}`")
    lines.append("")
    lines.append("## What this file is")
    lines.append("")
    lines.append("This is a front page, not the full memory store.")
    lines.append("It shows recent memories for this project so Codex can recover context at session start.")
    lines.append("For deeper recall, run the search command below.")
    lines.append("")
    lines.append("## Recent memories")
    lines.append("")
    if recent:
        for index, memory in enumerate(recent, start=1):
            lines.append(f"{index}. [{memory['created_at']}]")
            lines.append(f"   - Q: {short(memory['question'])}")
            lines.append(f"   - A: {short(memory['answer'])}")
    else:
        lines.append("No stored memories for this project yet.")
    lines.append("")
    lines.append("## Deep recall")
    lines.append("")
    lines.append("```bash")
    lines.append('"$HOME/.codex/memory-runtime/.venv/bin/python" "$HOME/.codex/bin/codex_memory.py" search --cwd "$PWD" --query "<topic>"')
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_memory_md(conn: sqlite3.Connection, cwd: Path) -> Path:
    path = find_project_root(cwd) / "MEMORY.md"
    path.write_text(render_memory_md(conn, cwd), encoding="utf-8")
    return path


def ingest_notify_payload(payload: dict) -> bool:
    if payload.get("type") != "agent-turn-complete":
        append_log(f"ignored payload type={payload.get('type')!r}")
        return False

    cwd_raw = payload.get("cwd")
    if not cwd_raw:
        append_log("ignored payload without cwd")
        return False
    cwd = Path(cwd_raw).resolve()

    input_messages = payload.get("input-messages") or []
    if isinstance(input_messages, list):
        question = "\n\n".join(str(item) for item in input_messages if item is not None).strip()
    else:
        question = str(input_messages).strip()

    answer = str(payload.get("last-assistant-message") or "").strip()
    if not question or not answer:
        append_log(
            f"ignored payload with empty question/answer question_len={len(question)} answer_len={len(answer)}",
            cwd=cwd,
        )
        return False

    conn = connect(cwd)
    try:
        inserted = store_memory(
            conn,
            cwd=cwd,
            thread_id=str(payload.get("thread-id") or ""),
            turn_id=str(payload.get("turn-id") or ""),
            question=question,
            answer=answer,
        )

        append_log(
            f"stored memory inserted={inserted} thread_id={str(payload.get('thread-id') or '-') or '-'} "
            f"turn_id={str(payload.get('turn-id') or '-') or '-'} "
            f"question_len={len(question)} answer_len={len(answer)}",
            cwd=cwd,
        )
        try:
            write_memory_md(conn, cwd)
        except OSError as exc:
            append_log(f"MEMORY.md write skipped: {exc}", cwd=cwd)
        return inserted
    finally:
        conn.close()


def cmd_init(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    conn = connect(cwd)
    try:
        inserted = sync_session_logs(conn, cwd)
        try:
            out = write_memory_md(conn, cwd)
        except OSError as exc:
            append_log(f"MEMORY.md write skipped during init: {exc}", cwd=cwd)
            out = find_project_root(cwd) / "MEMORY.md"
    finally:
        conn.close()
    print(f"session_sync_inserted={inserted}")
    print(out)
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.payload_json)
        stored = ingest_notify_payload(payload)
        append_log(
            f"notify handled stored={stored} type={payload.get('type')!r} cwd={payload.get('cwd')!r}"
        )
        return 0
    except Exception as exc:
        append_log(f"notify failed: {exc}")
        print(f"[codex_memory notify] {exc}", file=sys.stderr)
        return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    conn = connect(cwd)
    try:
        inserted = sync_session_logs(conn, cwd)
        backfill_embeddings(conn)
        try:
            out = write_memory_md(conn, cwd)
        except OSError as exc:
            append_log(f"MEMORY.md write skipped during refresh: {exc}", cwd=cwd)
            out = find_project_root(cwd) / "MEMORY.md"
    finally:
        conn.close()
    print(f"session_sync_inserted={inserted}")
    print(out)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    conn = connect(cwd)
    try:
        inserted = sync_session_logs(conn, cwd)
    finally:
        conn.close()
    print(f"session_sync_inserted={inserted}")
    print(db_path(cwd))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    conn = connect(cwd)
    try:
        sync_session_logs(conn, cwd)
        results = hybrid_search(conn, args.query, limit=args.limit)
    finally:
        conn.close()

    print("# Memory search results")
    print("")
    print(f"- project_root: `{find_project_root(cwd)}`")
    print(f"- project_db: `{db_path(cwd)}`")
    print(f"- query: {args.query}")
    print("")
    if not results:
        print("No matching memories.")
        return 0

    for index, memory in enumerate(results, start=1):
        print(f"## {index}. score={memory['score']:.6f} created_at={memory['created_at']}")
        print(f"- Q: {memory['question']}")
        print(f"- A: {memory['answer']}")
        print("")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Per-project long-term memory for Codex")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="initialize project memory DB and MEMORY.md")
    p_init.add_argument("--cwd", required=True)
    p_init.set_defaults(func=cmd_init)

    p_notify = sub.add_parser("notify", help="ingest Codex notify payload")
    p_notify.add_argument("payload_json")
    p_notify.set_defaults(func=cmd_notify)

    p_refresh = sub.add_parser("refresh", help="rebuild MEMORY.md and embed pending records")
    p_refresh.add_argument("--cwd", required=True)
    p_refresh.set_defaults(func=cmd_refresh)

    p_sync = sub.add_parser("sync", help="backfill memories from saved Codex session logs")
    p_sync.add_argument("--cwd", required=True)
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", help="hybrid search over this project's memory")
    p_search.add_argument("--cwd", required=True)
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--limit", type=int, default=SEARCH_LIMIT_DEFAULT)
    p_search.set_defaults(func=cmd_search)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

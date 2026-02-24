#!/usr/bin/env python3
"""
bench_memory.py
===============
Benchmarks for the cadre-ai SQLite memory store.

Tests: store throughput, keyword recall, FTS5 search latency,
engram cache hit/miss simulation, and DB size at various scales.

Uses temporary databases in /tmp — no side effects on the real memory DB.
"""

from __future__ import annotations

import sqlite3
import json
import os
import time
import random
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Schema — mirrors mcp-servers/claude-memory/src/server.py exactly
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    summary TEXT,
    project TEXT,
    tags TEXT,
    importance INTEGER DEFAULT 5,
    memory_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    embedding BLOB,
    user_id TEXT DEFAULT 'bench'
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, summary, tags, project,
    content='memories',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, summary, tags, project)
    VALUES (new.id, new.content, new.summary, new.tags, new.project);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags, project)
    VALUES('delete', old.id, old.content, old.summary, old.tags, old.project);
END;
"""


def _open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    # executescript handles multi-statement DDL including BEGIN...END triggers
    conn.executescript(_DDL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Sample data generators
# ---------------------------------------------------------------------------

_PROJECTS = ["cadre-ai", "revit-bridge", "devops", "general", "market-analysis"]
_MEMORY_TYPES = ["context", "correction", "insight", "pattern", "known-good"]
_TAGS_POOL = [
    "filesystem", "git", "deployment", "correction", "common-sense",
    "identity", "network", "execution", "scope", "known-good", "seed",
]
_CONTENT_TEMPLATES = [
    "CORRECTION [{sev}]: {action}\nWrong: {wrong}\nRight: {right}\nDomain: {domain}",
    "KNOWN GOOD: {action}\nContext: Verified in project {project}",
    "SEED CORRECTION [{id}]: {domain}\nWhat goes wrong: {wrong}\nCorrect approach: {right}",
    "Memory from session: {action}. Outcome was {right}. Tags: {tags}",
    "Agent recalled: {action}. Importance rated {imp}/10.",
]

_ACTIONS = [
    "deploy to /opt/app", "run git reset --hard", "delete all temp files",
    "push to main branch", "send email to user", "drop database table",
    "overwrite config file", "truncate logs", "publish release",
    "merge feature branch", "commit secrets to repo", "rm -rf build/",
    "update dependency versions", "read file before editing", "backup database",
    "validate schema before write", "check path exists", "confirm deployment target",
]

_DOMAINS = ["filesystem", "git", "network", "execution", "scope", "deployment", "data", "identity"]


def _random_content(idx: int) -> tuple[str, str, str, str, int, str]:
    """Return (content, summary, project, tags, importance, memory_type)."""
    action = random.choice(_ACTIONS)
    domain = random.choice(_DOMAINS)
    template = random.choice(_CONTENT_TEMPLATES)
    content = template.format(
        sev=random.choice(["HIGH", "MEDIUM", "LOW"]),
        action=action,
        wrong=f"Used wrong approach #{idx}",
        right=f"Correct approach verified in run {idx}",
        domain=domain,
        project=random.choice(_PROJECTS),
        id=f"{domain[:3].upper()}-{idx:03d}",
        tags=", ".join(random.sample(_TAGS_POOL, 3)),
        imp=random.randint(1, 10),
    )
    summary = f"Memory #{idx}: {action[:40]}"
    project = random.choice(_PROJECTS)
    tags = json.dumps(random.sample(_TAGS_POOL, random.randint(1, 4)))
    importance = random.randint(1, 10)
    memory_type = random.choice(_MEMORY_TYPES)
    return content, summary, project, tags, importance, memory_type


# ---------------------------------------------------------------------------
# Individual benchmarks
# ---------------------------------------------------------------------------

def bench_store(conn: sqlite3.Connection, count: int) -> dict:
    """Insert `count` memories and measure wall time."""
    rows = [_random_content(i) for i in range(count)]

    t0 = time.perf_counter()
    with conn:
        conn.executemany(
            """INSERT INTO memories
               (content, summary, project, tags, importance, memory_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
    elapsed = time.perf_counter() - t0

    total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return {
        "elapsed_s": round(elapsed, 6),
        "ops_per_s": round(count / elapsed),
        "total_rows": total,
    }


def bench_keyword_recall(conn: sqlite3.Connection, keyword: str, runs: int = 20) -> dict:
    """
    LIKE-based recall — same strategy as sense.py _search_sqlite().
    Averages `runs` queries.
    """
    timings = []
    for _ in range(runs):
        t0 = time.perf_counter()
        rows = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? ORDER BY importance DESC LIMIT 10",
            (f"%{keyword}%",),
        ).fetchall()
        timings.append(time.perf_counter() - t0)

    avg = sum(timings) / len(timings)
    return {
        "keyword": keyword,
        "avg_s": round(avg, 6),
        "min_s": round(min(timings), 6),
        "max_s": round(max(timings), 6),
        "results_returned": len(rows),
    }


def bench_fts5_search(conn: sqlite3.Connection, query: str, runs: int = 20) -> dict:
    """
    FTS5 full-text search via memories_fts virtual table.
    Averages `runs` queries.
    """
    timings = []
    row_count = 0
    for _ in range(runs):
        t0 = time.perf_counter()
        rows = conn.execute(
            """SELECT m.* FROM memories m
               JOIN memories_fts fts ON m.id = fts.rowid
               WHERE memories_fts MATCH ?
               ORDER BY rank LIMIT 10""",
            (query,),
        ).fetchall()
        timings.append(time.perf_counter() - t0)
        row_count = len(rows)

    avg = sum(timings) / len(timings)
    return {
        "query": query,
        "avg_s": round(avg, 6),
        "min_s": round(min(timings), 6),
        "max_s": round(max(timings), 6),
        "results_returned": row_count,
    }


def bench_engram_cache(conn: sqlite3.Connection, hot_set_size: int = 50, total_queries: int = 200) -> dict:
    """
    Simulate an engram cache: a hot set of recently-accessed memory IDs
    are re-queried by rowid (O(1) PK lookup). Measures hit/miss ratio
    and time difference.

    'hit' = rowid in hot set (fast PK lookup)
    'miss' = rowid not in hot set (full scan fallback)
    """
    all_ids = [r[0] for r in conn.execute("SELECT id FROM memories ORDER BY RANDOM() LIMIT 500").fetchall()]
    if len(all_ids) < hot_set_size:
        hot_set_size = max(1, len(all_ids) // 2)

    hot_ids = set(random.sample(all_ids, min(hot_set_size, len(all_ids))))
    query_ids = [random.choice(all_ids) for _ in range(total_queries)]

    hits, misses = 0, 0
    hit_times, miss_times = [], []

    for qid in query_ids:
        if qid in hot_ids:
            t0 = time.perf_counter()
            conn.execute("SELECT * FROM memories WHERE id = ?", (qid,)).fetchone()
            hit_times.append(time.perf_counter() - t0)
            hits += 1
        else:
            t0 = time.perf_counter()
            conn.execute("SELECT * FROM memories WHERE id = ?", (qid,)).fetchone()
            miss_times.append(time.perf_counter() - t0)
            misses += 1

    hit_avg = sum(hit_times) / max(len(hit_times), 1)
    miss_avg = sum(miss_times) / max(len(miss_times), 1)

    return {
        "total_queries": total_queries,
        "hot_set_size": hot_set_size,
        "hits": hits,
        "misses": misses,
        "hit_ratio": round(hits / total_queries, 3),
        "avg_hit_s": round(hit_avg, 6),
        "avg_miss_s": round(miss_avg, 6),
        "speedup": round(miss_avg / max(hit_avg, 1e-9), 2) if hit_avg > 0 else "N/A",
    }


def bench_db_size(db_path: str) -> dict:
    """Report database file size on disk after flushing the WAL."""
    # Checkpoint WAL so all data lands in the main DB file
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
    conn.close()

    # Sum main file + any remaining WAL
    size_bytes = os.path.getsize(db_path)
    wal_path = db_path + "-wal"
    if os.path.exists(wal_path):
        size_bytes += os.path.getsize(wal_path)

    row_count = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return {
        "size_kb": round(size_bytes / 1024, 1),
        "size_mb": round(size_bytes / 1024 / 1024, 3),
        "row_count": row_count,
        "bytes_per_row": round(size_bytes / max(row_count, 1)),
    }


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------

def run(verbose: bool = False) -> list[dict]:
    """Run all memory benchmarks. Returns list of result dicts."""
    results = []
    db_fd, db_path = tempfile.mkstemp(prefix="bench_memory_", suffix=".db", dir="/tmp")
    os.close(db_fd)

    try:
        conn = _open_db(db_path)

        tiers = [100, 1000, 10000]
        current_count = 0

        for tier in tiers:
            batch = tier - current_count

            # --- Store benchmark ---
            store_res = bench_store(conn, batch)
            current_count = store_res["total_rows"]
            results.append({
                "benchmark": f"store_{tier}",
                "label": f"Insert {batch} rows (total {current_count})",
                "elapsed_s": store_res["elapsed_s"],
                "ops_per_s": store_res["ops_per_s"],
                "detail": store_res,
            })
            if verbose:
                print(f"  [store_{tier}] {store_res['elapsed_s']:.4f}s | {store_res['ops_per_s']:,} ops/s")

            # --- Keyword recall ---
            kw = random.choice(["CORRECTION", "deployment", "git", "filesystem", "delete"])
            kw_res = bench_keyword_recall(conn, kw)
            results.append({
                "benchmark": f"keyword_recall_{tier}",
                "label": f"Keyword recall '{kw}' at {current_count} rows",
                "elapsed_s": kw_res["avg_s"],
                "detail": kw_res,
            })
            if verbose:
                print(f"  [keyword_{tier}] avg {kw_res['avg_s']*1000:.2f}ms | {kw_res['results_returned']} results")

            # --- FTS5 search ---
            fts_queries = ["correct approach", "deployment target", "git reset", "filesystem delete"]
            fts_query = random.choice(fts_queries)
            fts_res = bench_fts5_search(conn, fts_query)
            results.append({
                "benchmark": f"fts5_search_{tier}",
                "label": f"FTS5 '{fts_query}' at {current_count} rows",
                "elapsed_s": fts_res["avg_s"],
                "detail": fts_res,
            })
            if verbose:
                print(f"  [fts5_{tier}] avg {fts_res['avg_s']*1000:.2f}ms | {fts_res['results_returned']} results")

            # --- Engram cache ---
            cache_res = bench_engram_cache(conn)
            results.append({
                "benchmark": f"engram_cache_{tier}",
                "label": f"Engram cache simulation at {current_count} rows",
                "elapsed_s": cache_res["avg_hit_s"],
                "hit_ratio": cache_res["hit_ratio"],
                "detail": cache_res,
            })
            if verbose:
                print(f"  [cache_{tier}] hit_ratio={cache_res['hit_ratio']:.1%} | hit={cache_res['avg_hit_s']*1000:.3f}ms | miss={cache_res['avg_miss_s']*1000:.3f}ms")

            # --- DB size ---
            size_res = bench_db_size(db_path)
            results.append({
                "benchmark": f"db_size_{tier}",
                "label": f"DB size at {current_count} rows",
                "size_kb": size_res["size_kb"],
                "bytes_per_row": size_res["bytes_per_row"],
                "detail": size_res,
            })
            if verbose:
                print(f"  [db_size_{tier}] {size_res['size_kb']} KB | {size_res['bytes_per_row']} bytes/row")

        conn.close()

    finally:
        try:
            os.unlink(db_path)
            wal = db_path + "-wal"
            shm = db_path + "-shm"
            for f in [wal, shm]:
                if os.path.exists(f):
                    os.unlink(f)
        except OSError:
            pass

    return results


if __name__ == "__main__":
    print("Running memory benchmarks standalone...\n")
    results = run(verbose=True)
    print(f"\nDone. {len(results)} benchmark results collected.")

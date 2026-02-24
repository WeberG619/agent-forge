# Cadre-AI Benchmark Suite

Performance benchmarks for the core subsystems of cadre-ai. Covers the memory
engine, common sense engine, and agent system. All benchmarks use only Python
stdlib + sqlite3 — no external dependencies required.

---

## Suites

| Suite | File | What It Measures |
|-------|------|-----------------|
| `memory` | `bench_memory.py` | SQLite store/recall latency, FTS5 search, cache simulation, DB size |
| `sense` | `bench_sense.py` | Seed-matching throughput, confidence scoring, known-block accuracy |
| `agents` | `bench_agents.py` | Agent definition parse time, schema validation, dispatch routing overhead |

---

## Quick Start

Run all suites:

```bash
python benchmarks/run_benchmarks.py
```

Run a single suite:

```bash
python benchmarks/run_benchmarks.py --suite memory
python benchmarks/run_benchmarks.py --suite sense
python benchmarks/run_benchmarks.py --suite agents
```

Save results to JSON:

```bash
python benchmarks/run_benchmarks.py --json results.json
```

---

## Benchmark Details

### bench_memory.py

Tests the SQLite-backed memory store used by `mcp-servers/claude-memory/`.

- **Store throughput** — Inserts 100 / 1,000 / 10,000 rows and reports ops/sec
- **Keyword recall latency** — LIKE-based recall at each DB size
- **FTS5 search latency** — Full-text search (memories_fts virtual table) at each DB size
- **Engram cache simulation** — Hit/miss ratio when a hot set of IDs is re-queried by rowid
- **DB size on disk** — Reports file size in KB after each population tier

All tests use a throw-away database in `/tmp/bench_memory_*.db`.

### bench_sense.py

Tests `framework/common-sense/sense.py` in isolation, without a live MCP server.

- **Check throughput** — Runs `cs.before()` on 100 representative actions and reports ops/sec
- **Seed matching accuracy** — Verifies that each known-blocked seed pattern is caught
- **Confidence scoring consistency** — Checks that confidence values are bounded [0, 1] and
  that destructive actions always score lower than benign ones

Seeds are loaded from the real `framework/common-sense/seeds.json`.

### bench_agents.py

Tests the agent layer (no live Claude API calls).

- **Parse time** — Reads all `.md` and `.yaml` agent definitions from `agents/`
- **Schema validation** — Validates that each agent file contains required header fields
- **Dispatch routing simulation** — Simulates keyword-based routing overhead across all agents

---

## Output Format

Results are printed as an aligned table to stdout:

```
Suite         Benchmark                      Result
------------- ------------------------------ --------------------
memory        store_100                      0.012 s / 8333 ops/s
memory        fts5_search_1000               0.003 s / 333333 ops/s
...
```

System metadata (Python version, OS, RAM) is printed at the top of every run.

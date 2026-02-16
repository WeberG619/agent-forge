# Claude Memory MCP Server

Persistent long-term memory for Claude Code sessions. Stores decisions, corrections, preferences, and project context in a local SQLite database with semantic search.

## Features

- **Persistent memory** across sessions (SQLite + FTS5)
- **Semantic search** using embeddings (BAAI/bge-small-en-v1.5)
- **Correction tracking** - learns from your corrections
- **Project isolation** - memories scoped by project
- **Knowledge graph** - link related memories
- **Multi-user support** - isolated memory per user
- **Engram cache** - O(1) hash-based fast path for repeated queries
- **Auto-backup** with integrity verification

## Setup

```bash
pip install -r requirements.txt
```

For semantic search (optional but recommended):
```bash
pip install fastembed numpy
```

## Tools

### Core
| Tool | Description |
|------|-------------|
| `memory_store` | Store a new memory |
| `memory_recall` | Recall memories by keyword |
| `memory_semantic_search` | Search by meaning (requires fastembed) |
| `memory_forget` | Delete a specific memory |
| `memory_stats` | Get memory statistics |

### Corrections
| Tool | Description |
|------|-------------|
| `memory_store_correction` | Store a correction (what was wrong, what's right) |
| `memory_get_corrections` | Get corrections for a topic |
| `memory_check_before_action` | Pre-flight check before taking action |

### Context
| Tool | Description |
|------|-------------|
| `memory_smart_context` | Get relevant context for current work |
| `memory_smart_recall` | Intelligent recall combining FTS + semantic |
| `memory_get_related` | Get memories linked to a given memory |
| `memory_link` | Create relationship between memories |

### Projects
| Tool | Description |
|------|-------------|
| `memory_get_project` | Get project details |
| `memory_list_projects` | List all projects |
| `memory_update_project` | Update project info |

### Session
| Tool | Description |
|------|-------------|
| `memory_summarize_session` | Summarize current session |

### Maintenance
| Tool | Description |
|------|-------------|
| `memory_compact` | Merge duplicate/similar memories |
| `memory_verify` | Verify a memory's accuracy |
| `memory_find_patterns` | Find recurring patterns |
| `memory_synthesize_patterns` | Synthesize patterns into insights |

## Configuration

Add to your `settings.local.json`:

```json
{
  "mcpServers": {
    "claude-memory": {
      "command": "python3",
      "args": ["/path/to/claude-memory/src/server.py"],
      "disabled": false
    }
  }
}
```

## Data Storage

- Database: `data/memories.db` (SQLite with WAL mode)
- Backups: `data/backups/` (automatic hourly backups)
- The database is created automatically on first run

## Notes

- No external services required - everything runs locally
- Semantic search is optional but greatly improves recall quality
- Memory importance is on a 1-10 scale (10 = critical corrections)
- Memories can be scoped to projects or global
- Supports automatic expiration via `expires_at` parameter

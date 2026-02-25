#!/usr/bin/env python3
"""
Claude Memory MCP Server
Provides persistent memory storage and retrieval for Claude Code sessions.
Supports multi-user isolation with shared knowledge base.
"""

import json
import sqlite3
import os
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional
from mcp.server.fastmcp import FastMCP

# =============================================================================
# USER DETECTION
# =============================================================================

_current_user: Optional[str] = None

def get_current_user() -> str:
    """
    Get current user ID from config or environment.

    Priority:
    1. CLAUDE_USER_ID environment variable
    2. ~/.claude/user.json file
    3. System username as fallback
    """
    global _current_user

    if _current_user is not None:
        return _current_user

    # Check environment variable first
    if os.environ.get('CLAUDE_USER_ID'):
        _current_user = os.environ['CLAUDE_USER_ID']
        return _current_user

    # Check user config file
    user_config = Path.home() / ".claude" / "user.json"
    if user_config.exists():
        try:
            with open(user_config, 'r') as f:
                config = json.load(f)
                if config.get('user_id'):
                    _current_user = config['user_id']
                    return _current_user
        except Exception:
            pass

    # Fallback to system username
    import getpass
    _current_user = getpass.getuser()
    return _current_user


def set_current_user(user_id: str) -> None:
    """Set current user ID (for testing or explicit override)."""
    global _current_user
    _current_user = user_id

# Lazy load embedding model to avoid slow startup
_embedding_model = None

def get_embedding_model():
    """Lazy load the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
            _embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception as e:
            print(f"Warning: Could not load embedding model: {e}")
            return None
    return _embedding_model

def generate_embedding(text: str) -> bytes:
    """Generate embedding for text and return as bytes for storage."""
    model = get_embedding_model()
    if model is None:
        return None

    embeddings = list(model.embed([text]))
    if embeddings:
        return np.array(embeddings[0]).tobytes()
    return None

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Initialize FastMCP server
mcp = FastMCP("claude-memory")

# Database path - use relative path from server location for portability
_SERVER_DIR = Path(__file__).parent.parent
DB_PATH = _SERVER_DIR / "data" / "memories.db"

def get_db():
    """Get database connection with row factory and crash protection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Enable WAL mode for crash protection and better concurrency
    conn.execute("PRAGMA journal_mode = WAL")
    # Ensure data is written to disk
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

def verify_database_integrity():
    """Check database integrity and attempt recovery if needed."""

    if not DB_PATH.exists():
        print("Database does not exist, will be created.")
        return True

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            print(f"Database integrity check: OK ({DB_PATH})")
            return True
        else:
            print(f"WARNING: Database integrity check failed: {result}")
            # Try to recover from backup
            return attempt_recovery()
    except Exception as e:
        print(f"ERROR checking database: {e}")
        return attempt_recovery()


def attempt_recovery():
    """Attempt to recover database from most recent backup."""
    import shutil
    from glob import glob

    backup_dir = DB_PATH.parent.parent / "backups" / "hourly"
    backups = sorted(glob(str(backup_dir / "memory_*.db")), reverse=True)

    if not backups:
        print("No backups found for recovery!")
        return False

    print(f"Attempting recovery from: {backups[0]}")

    # Backup corrupt database
    corrupt_path = DB_PATH.with_suffix(".db.corrupt")
    if DB_PATH.exists():
        shutil.move(DB_PATH, corrupt_path)
        print(f"Moved corrupt database to: {corrupt_path}")

    # Restore from backup
    shutil.copy2(backups[0], DB_PATH)
    print(f"Restored from backup: {backups[0]}")

    # Verify restored database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories;")
        count = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            print(f"Recovery successful! Restored {count} memories.")
            return True
        else:
            print("Recovery failed - backup also corrupt!")
            return False
    except Exception as e:
        print(f"Recovery failed: {e}")
        return False


def init_database():
    """Initialize the database schema with integrity verification."""
    # First, verify existing database integrity
    if not verify_database_integrity():
        print("WARNING: Starting with potentially compromised database!")

    conn = get_db()
    cursor = conn.cursor()

    # Core memories table
    cursor.execute("""
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
            user_id TEXT DEFAULT 'default'
        )
    """)

    # Add embedding column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN embedding BLOB")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add user_id column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN user_id TEXT DEFAULT 'default'")
        # Migrate existing memories to current user
        current_user = get_current_user()
        cursor.execute("UPDATE memories SET user_id = ? WHERE user_id = 'default'", (current_user,))
        print(f"Migrated existing memories to user: {current_user}")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add effectiveness tracking columns for self-improvement loop
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN times_surfaced INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN times_helped INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN last_tested TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN effectiveness_score REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass

    # Full-text search virtual table
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content, summary, tags, project,
            content='memories',
            content_rowid='id'
        )
    """)

    # Triggers to keep FTS in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content, summary, tags, project)
            VALUES (new.id, new.content, new.summary, new.tags, new.project);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags, project)
            VALUES('delete', old.id, old.content, old.summary, old.tags, old.project);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags, project)
            VALUES('delete', old.id, old.content, old.summary, old.tags, old.project);
            INSERT INTO memories_fts(rowid, content, summary, tags, project)
            VALUES (new.id, new.content, new.summary, new.tags, new.project);
        END
    """)

    # Projects tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            user_id TEXT DEFAULT 'default',
            UNIQUE(name, user_id)
        )
    """)

    # Add user_id column to projects if it doesn't exist
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN user_id TEXT DEFAULT 'default'")
        current_user = get_current_user()
        cursor.execute("UPDATE projects SET user_id = ? WHERE user_id = 'default'", (current_user,))
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Sessions history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            project TEXT,
            summary TEXT,
            memories_created INTEGER DEFAULT 0,
            user_id TEXT DEFAULT 'default'
        )
    """)

    # Add user_id column to sessions if it doesn't exist
    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT 'default'")
        current_user = get_current_user()
        cursor.execute("UPDATE sessions SET user_id = ? WHERE user_id = 'default'", (current_user,))
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Memory relationships table for knowledge graph
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            strength REAL DEFAULT 1.0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES memories(id) ON DELETE CASCADE,
            FOREIGN KEY (target_id) REFERENCES memories(id) ON DELETE CASCADE,
            UNIQUE(source_id, target_id, relationship_type)
        )
    """)

    # Indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_source ON memory_relationships(source_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_target ON memory_relationships(target_id)")

    conn.commit()
    conn.close()

# Initialize database on module load
init_database()


@mcp.tool()
def memory_store(
    content: str,
    project: str = None,
    tags: list[str] = None,
    importance: int = 5,
    memory_type: str = "context",
    summary: str = None,
    namespace: str = "global",
    verified: bool = False,
    expires_at: str = None,
    source: str = "manual"
) -> str:
    """
    Store a new memory.

    Args:
        content: The full content of the memory
        project: Project name this memory relates to
        tags: List of tags for categorization
        importance: 1-10 scale (10 = critical)
        memory_type: One of: decision, fact, preference, context, outcome, error
        summary: Brief summary (auto-generated if not provided)
        namespace: Scope isolation (global | project:<name> | machine | revit)
        verified: Whether this memory has been verified as accurate
        expires_at: Optional ISO8601 timestamp for automatic expiration
        source: Origin of memory (manual | auto | tool)

    Returns:
        Confirmation with memory ID
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    tags_json = json.dumps(tags) if tags else None

    # Auto-generate summary if not provided
    if not summary and len(content) > 200:
        summary = content[:200] + "..."

    # Generate embedding for semantic search
    embedding = generate_embedding(content)

    # Auto-set namespace from project if not specified
    if namespace == "global" and project:
        namespace = f"project:{project}"

    cursor.execute("""
        INSERT INTO memories (content, summary, project, tags, importance, memory_type, embedding, namespace, verified, expires_at, source, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (content, summary, project, tags_json, importance, memory_type, embedding, namespace, 1 if verified else 0, expires_at, source, user_id))

    memory_id = cursor.lastrowid

    # Update project last_accessed if project specified
    if project:
        cursor.execute("""
            INSERT INTO projects (name, last_accessed, user_id)
            VALUES (?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(name, user_id) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
        """, (project, user_id))

    conn.commit()
    conn.close()

    return f"Memory stored with ID {memory_id} [user: {user_id}, project: {project or 'none'}, type: {memory_type}, importance: {importance}]"


@mcp.tool()
def memory_recall(
    query: str,
    project: str = None,
    memory_type: str = None,
    limit: int = 10,
    min_importance: int = 1
) -> str:
    """
    Search memories using full-text search.

    Args:
        query: Search query (supports FTS5 syntax)
        project: Filter by project name
        memory_type: Filter by type (decision, fact, preference, context, outcome, error)
        limit: Maximum results to return
        min_importance: Minimum importance level (1-10)

    Returns:
        Matching memories with relevance scores
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Build the query
    sql = """
        SELECT
            m.id,
            m.content,
            m.summary,
            m.project,
            m.tags,
            m.importance,
            m.memory_type,
            m.created_at,
            m.access_count,
            bm25(memories_fts) as relevance
        FROM memories_fts
        JOIN memories m ON memories_fts.rowid = m.id
        WHERE memories_fts MATCH ?
        AND m.importance >= ?
        AND m.user_id = ?
    """

    params = [query, min_importance, user_id]

    if project:
        sql += " AND m.project = ?"
        params.append(project)

    if memory_type:
        sql += " AND m.memory_type = ?"
        params.append(memory_type)

    sql += " ORDER BY relevance LIMIT ?"
    params.append(limit)

    try:
        cursor.execute(sql, params)
        results = cursor.fetchall()
    except sqlite3.OperationalError as e:
        conn.close()
        return f"Search error: {e}. Try simpler search terms."

    if not results:
        conn.close()
        return f"No memories found matching '{query}'"

    # Update access counts
    for row in results:
        cursor.execute("""
            UPDATE memories
            SET accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1
            WHERE id = ?
        """, (row['id'],))

    conn.commit()
    conn.close()

    # Format results
    output = [f"Found {len(results)} memories:\n"]

    for row in results:
        tags = json.loads(row['tags']) if row['tags'] else []
        output.append(f"""
---
**ID {row['id']}** | {row['memory_type']} | Importance: {row['importance']}/10
Project: {row['project'] or 'none'} | Tags: {', '.join(tags) if tags else 'none'}
Created: {row['created_at']}

{row['content']}
""")

    return '\n'.join(output)


@mcp.tool()
def memory_semantic_search(
    query: str,
    project: str = None,
    limit: int = 10,
    min_similarity: float = 0.5
) -> str:
    """
    Search memories by MEANING, not just keywords. Use this when keyword search fails
    to find what you're looking for.

    Args:
        query: Natural language description of what you're looking for
        project: Filter by project name
        limit: Maximum results to return
        min_similarity: Minimum similarity score (0-1, default 0.5)

    Returns:
        Semantically similar memories ranked by relevance
    """
    # Generate embedding for query
    query_embedding = generate_embedding(query)

    if query_embedding is None:
        return "Semantic search unavailable - embedding model not loaded. Use memory_recall for keyword search."

    query_vec = np.frombuffer(query_embedding, dtype=np.float32)

    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Get all memories with embeddings for this user
    sql = "SELECT id, content, summary, project, tags, importance, memory_type, created_at, embedding FROM memories WHERE embedding IS NOT NULL AND user_id = ?"
    params = [user_id]

    if project:
        sql += " AND project = ?"
        params.append(project)

    cursor.execute(sql, params)
    results = cursor.fetchall()

    if not results:
        conn.close()
        return "No memories with embeddings found. Store new memories to enable semantic search."

    # Calculate similarities
    scored_results = []
    for row in results:
        if row['embedding']:
            mem_vec = np.frombuffer(row['embedding'], dtype=np.float32)
            similarity = cosine_similarity(query_vec, mem_vec)
            if similarity >= min_similarity:
                scored_results.append((similarity, row))

    # Sort by similarity
    scored_results.sort(key=lambda x: x[0], reverse=True)
    scored_results = scored_results[:limit]

    if not scored_results:
        conn.close()
        return f"No memories found with similarity >= {min_similarity}. Try lowering min_similarity or use keyword search."

    # Update access counts
    for _, row in scored_results:
        cursor.execute("""
            UPDATE memories
            SET accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1
            WHERE id = ?
        """, (row['id'],))

    conn.commit()
    conn.close()

    # Format results
    output = [f"# Semantic Search Results ({len(scored_results)} found)\n"]
    output.append(f"Query: \"{query}\"\n")

    for similarity, row in scored_results:
        tags = json.loads(row['tags']) if row['tags'] else []
        output.append(f"""
---
**ID {row['id']}** | Similarity: {similarity:.2%} | {row['memory_type']}
Project: {row['project'] or 'none'} | Importance: {row['importance']}/10
Tags: {', '.join(tags) if tags else 'none'}

{row['content'][:500]}{'...' if len(row['content']) > 500 else ''}
""")

    return '\n'.join(output)


@mcp.tool()
def memory_link(
    source_id: int,
    target_id: int,
    relationship_type: str,
    strength: float = 1.0,
    notes: str = None
) -> str:
    """
    Create a relationship between two memories. This builds a knowledge graph
    that helps understand how ideas connect.

    Args:
        source_id: ID of the source memory
        target_id: ID of the target memory
        relationship_type: Type of relationship:
            - "depends_on": Source depends on target
            - "evolved_from": Source evolved from target
            - "contradicts": Source contradicts target
            - "supports": Source supports target
            - "part_of": Source is part of target
            - "related_to": General relationship
        strength: Relationship strength (0-1, default 1.0)
        notes: Optional notes about the relationship

    Returns:
        Confirmation of relationship creation
    """
    conn = get_db()
    cursor = conn.cursor()

    # Verify both memories exist
    cursor.execute("SELECT id FROM memories WHERE id = ?", (source_id,))
    if not cursor.fetchone():
        conn.close()
        return f"Source memory {source_id} not found"

    cursor.execute("SELECT id FROM memories WHERE id = ?", (target_id,))
    if not cursor.fetchone():
        conn.close()
        return f"Target memory {target_id} not found"

    try:
        cursor.execute("""
            INSERT INTO memory_relationships (source_id, target_id, relationship_type, strength, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, target_id, relationship_type, strength, notes))

        conn.commit()
        conn.close()
        return f"Linked memory {source_id} --[{relationship_type}]--> {target_id}"

    except sqlite3.IntegrityError:
        conn.close()
        return f"Relationship already exists between {source_id} and {target_id} of type {relationship_type}"


@mcp.tool()
def memory_get_related(
    memory_id: int,
    relationship_types: list[str] = None,
    depth: int = 1
) -> str:
    """
    Get memories related to a specific memory through the knowledge graph.

    Args:
        memory_id: ID of the memory to find relations for
        relationship_types: Filter by types (depends_on, evolved_from, contradicts, supports, part_of, related_to)
        depth: How many levels deep to traverse (1-3)

    Returns:
        Related memories with relationship information
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get the source memory
    cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
    source = cursor.fetchone()
    if not source:
        conn.close()
        return f"Memory {memory_id} not found"

    output = [f"# Related Memories for ID {memory_id}\n"]
    output.append(f"**Source**: {source['content'][:100]}...\n")

    visited = {memory_id}
    current_level = [memory_id]

    for level in range(depth):
        if not current_level:
            break

        output.append(f"\n## Level {level + 1} Connections\n")
        next_level = []

        for mid in current_level:
            # Get outgoing relationships
            sql = """
                SELECT r.*, m.content, m.project, m.memory_type, m.importance
                FROM memory_relationships r
                JOIN memories m ON r.target_id = m.id
                WHERE r.source_id = ?
            """
            params = [mid]

            if relationship_types:
                placeholders = ','.join('?' * len(relationship_types))
                sql += f" AND r.relationship_type IN ({placeholders})"
                params.extend(relationship_types)

            cursor.execute(sql, params)

            for row in cursor.fetchall():
                if row['target_id'] not in visited:
                    visited.add(row['target_id'])
                    next_level.append(row['target_id'])
                    output.append(f"- **ID {row['target_id']}** --[{row['relationship_type']}]--> (strength: {row['strength']})")
                    output.append(f"  Type: {row['memory_type']} | Project: {row['project'] or 'none'}")
                    output.append(f"  {row['content'][:150]}...")
                    if row['notes']:
                        output.append(f"  *Note: {row['notes']}*")
                    output.append("")

            # Get incoming relationships
            sql = """
                SELECT r.*, m.content, m.project, m.memory_type, m.importance
                FROM memory_relationships r
                JOIN memories m ON r.source_id = m.id
                WHERE r.target_id = ?
            """
            params = [mid]

            if relationship_types:
                placeholders = ','.join('?' * len(relationship_types))
                sql += f" AND r.relationship_type IN ({placeholders})"
                params.extend(relationship_types)

            cursor.execute(sql, params)

            for row in cursor.fetchall():
                if row['source_id'] not in visited:
                    visited.add(row['source_id'])
                    next_level.append(row['source_id'])
                    output.append(f"- **ID {row['source_id']}** <--[{row['relationship_type']}]-- (strength: {row['strength']})")
                    output.append(f"  Type: {row['memory_type']} | Project: {row['project'] or 'none'}")
                    output.append(f"  {row['content'][:150]}...")
                    if row['notes']:
                        output.append(f"  *Note: {row['notes']}*")
                    output.append("")

        current_level = next_level

    conn.close()

    if len(output) == 2:
        output.append("No relationships found for this memory.")

    return '\n'.join(output)


@mcp.tool()
def memory_get_context(
    project: str = None,
    include_recent: bool = True,
    include_important: bool = True,
    include_decisions: bool = True,
    limit: int = 20
) -> str:
    """
    Get relevant context for session start. Call this at the beginning of each session.

    Args:
        project: Focus on specific project (if known)
        include_recent: Include recently created memories
        include_important: Include high-importance memories
        include_decisions: Include decision-type memories
        limit: Maximum total memories to return

    Returns:
        Formatted context for session initialization
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    memories = []

    # Get recent memories
    if include_recent:
        sql = """
            SELECT * FROM memories
            WHERE created_at > datetime('now', '-7 days')
            AND user_id = ?
        """
        if project:
            sql += " AND project = ?"
            cursor.execute(sql + " ORDER BY created_at DESC LIMIT ?", (user_id, project, limit // 3))
        else:
            cursor.execute(sql + " ORDER BY created_at DESC LIMIT ?", (user_id, limit // 3,))
        memories.extend(cursor.fetchall())

    # Get important memories
    if include_important:
        sql = "SELECT * FROM memories WHERE importance >= 7 AND user_id = ?"
        if project:
            sql += " AND project = ?"
            cursor.execute(sql + " ORDER BY importance DESC LIMIT ?", (user_id, project, limit // 3))
        else:
            cursor.execute(sql + " ORDER BY importance DESC LIMIT ?", (user_id, limit // 3,))
        memories.extend(cursor.fetchall())

    # Get decisions
    if include_decisions:
        sql = "SELECT * FROM memories WHERE memory_type = 'decision' AND user_id = ?"
        if project:
            sql += " AND project = ?"
            cursor.execute(sql + " ORDER BY created_at DESC LIMIT ?", (user_id, project, limit // 3))
        else:
            cursor.execute(sql + " ORDER BY created_at DESC LIMIT ?", (user_id, limit // 3,))
        memories.extend(cursor.fetchall())

    # Get project info if specified
    project_info = None
    if project:
        cursor.execute("SELECT * FROM projects WHERE name = ? AND user_id = ?", (project, user_id))
        project_info = cursor.fetchone()

    conn.close()

    # Deduplicate
    seen_ids = set()
    unique_memories = []
    for m in memories:
        if m['id'] not in seen_ids:
            seen_ids.add(m['id'])
            unique_memories.append(m)

    if not unique_memories and not project_info:
        return "No context available. This appears to be a fresh start."

    # Format output
    output = ["# Session Context\n"]

    if project_info:
        output.append(f"""
## Active Project: {project_info['name']}
- Path: {project_info['path'] or 'not set'}
- Status: {project_info['status']}
- Last accessed: {project_info['last_accessed']}
- Description: {project_info['description'] or 'none'}
""")

    if unique_memories:
        output.append(f"\n## Relevant Memories ({len(unique_memories)} loaded)\n")

        for m in unique_memories[:limit]:
            tags = json.loads(m['tags']) if m['tags'] else []
            output.append(f"""
### [{m['memory_type'].upper()}] {m['summary'] or m['content'][:100]}
- ID: {m['id']} | Importance: {m['importance']}/10 | Project: {m['project'] or 'general'}
- Tags: {', '.join(tags) if tags else 'none'}
- Created: {m['created_at']}

{m['content']}
""")

    return '\n'.join(output)


@mcp.tool()
def memory_get_project(project: str, include_all: bool = False) -> str:
    """
    Get complete history for a specific project.

    Args:
        project: Project name
        include_all: Include all memories (not just important ones)

    Returns:
        Project information and all related memories
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Get project info
    cursor.execute("SELECT * FROM projects WHERE name = ? AND user_id = ?", (project, user_id))
    project_info = cursor.fetchone()

    # Get memories
    if include_all:
        cursor.execute("""
            SELECT * FROM memories
            WHERE project = ? AND user_id = ?
            ORDER BY created_at DESC
        """, (project, user_id))
    else:
        cursor.execute("""
            SELECT * FROM memories
            WHERE project = ? AND user_id = ? AND (importance >= 5 OR memory_type = 'decision')
            ORDER BY importance DESC, created_at DESC
        """, (project, user_id))

    memories = cursor.fetchall()

    # Update project last_accessed
    cursor.execute("""
        UPDATE projects SET last_accessed = CURRENT_TIMESTAMP WHERE name = ? AND user_id = ?
    """, (project, user_id))

    conn.commit()
    conn.close()

    if not project_info and not memories:
        return f"No information found for project '{project}'"

    # Format output
    output = [f"# Project: {project}\n"]

    if project_info:
        output.append(f"""
## Project Info
- Path: {project_info['path'] or 'not set'}
- Status: {project_info['status']}
- Created: {project_info['created_at']}
- Last accessed: {project_info['last_accessed']}
- Description: {project_info['description'] or 'none'}
""")

    if memories:
        output.append(f"\n## Memories ({len(memories)} total)\n")

        # Group by type
        by_type = {}
        for m in memories:
            t = m['memory_type'] or 'context'
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(m)

        for mtype, mems in by_type.items():
            output.append(f"\n### {mtype.upper()} ({len(mems)})\n")
            for m in mems:
                output.append(f"- **[{m['importance']}/10]** {m['content'][:200]}{'...' if len(m['content']) > 200 else ''}\n")

    return '\n'.join(output)


@mcp.tool()
def memory_list_projects() -> str:
    """
    List all known projects with their status and memory counts.

    Returns:
        Table of all projects
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    cursor.execute("""
        SELECT
            p.name,
            p.path,
            p.status,
            p.last_accessed,
            COUNT(m.id) as memory_count,
            MAX(m.created_at) as last_memory
        FROM projects p
        LEFT JOIN memories m ON p.name = m.project AND m.user_id = ?
        WHERE p.user_id = ?
        GROUP BY p.name
        ORDER BY p.last_accessed DESC
    """, (user_id, user_id))

    projects = cursor.fetchall()
    conn.close()

    if not projects:
        return "No projects registered yet."

    output = ["# Known Projects\n"]
    output.append("| Project | Status | Memories | Last Accessed |")
    output.append("|---------|--------|----------|---------------|")

    for p in projects:
        output.append(f"| {p['name']} | {p['status']} | {p['memory_count']} | {p['last_accessed'] or 'never'} |")

    return '\n'.join(output)


@mcp.tool()
def memory_update_project(
    name: str,
    path: str = None,
    description: str = None,
    status: str = None
) -> str:
    """
    Update or create a project record.

    Args:
        name: Project name (required)
        path: File system path to project
        description: Project description
        status: Project status (active, paused, completed, archived)

    Returns:
        Confirmation
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Check if exists for this user
    cursor.execute("SELECT * FROM projects WHERE name = ? AND user_id = ?", (name, user_id))
    existing = cursor.fetchone()

    if existing:
        # Update
        updates = []
        params = []

        if path is not None:
            updates.append("path = ?")
            params.append(path)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if status is not None:
            updates.append("status = ?")
            params.append(status)

        updates.append("last_accessed = CURRENT_TIMESTAMP")
        params.append(name)
        params.append(user_id)

        cursor.execute(f"UPDATE projects SET {', '.join(updates)} WHERE name = ? AND user_id = ?", params)
        action = "updated"
    else:
        # Create
        cursor.execute("""
            INSERT INTO projects (name, path, description, status, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, path, description, status or 'active', user_id))
        action = "created"

    conn.commit()
    conn.close()

    return f"Project '{name}' {action} successfully for user {user_id}"


@mcp.tool()
def memory_forget(memory_id: int = None, query: str = None, confirm: bool = False) -> str:
    """
    Delete memories. Requires confirmation.

    Args:
        memory_id: Specific memory ID to delete
        query: Delete all memories matching this search
        confirm: Must be True to actually delete

    Returns:
        Deletion result or preview
    """
    if not confirm:
        return "Set confirm=True to actually delete memories. This action cannot be undone."

    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation - only delete user's own memories
    user_id = get_current_user()

    if memory_id:
        cursor.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
        deleted = cursor.rowcount
    elif query:
        cursor.execute("""
            DELETE FROM memories WHERE id IN (
                SELECT m.id FROM memories_fts
                JOIN memories m ON memories_fts.rowid = m.id
                WHERE memories_fts MATCH ? AND m.user_id = ?
            )
        """, (query, user_id))
        deleted = cursor.rowcount
    else:
        conn.close()
        return "Specify either memory_id or query to delete"

    conn.commit()
    conn.close()

    return f"Deleted {deleted} memories"


@mcp.tool()
def memory_stats() -> str:
    """
    Get memory system statistics.

    Returns:
        Statistics about stored memories
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Total memories for this user
    cursor.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,))
    total = cursor.fetchone()[0]

    # By type
    cursor.execute("""
        SELECT memory_type, COUNT(*) as count
        FROM memories
        WHERE user_id = ?
        GROUP BY memory_type
        ORDER BY count DESC
    """, (user_id,))
    by_type = cursor.fetchall()

    # By project
    cursor.execute("""
        SELECT project, COUNT(*) as count
        FROM memories
        WHERE project IS NOT NULL AND user_id = ?
        GROUP BY project
        ORDER BY count DESC
        LIMIT 10
    """, (user_id,))
    by_project = cursor.fetchall()

    # Recent activity
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM memories
        WHERE created_at > datetime('now', '-30 days') AND user_id = ?
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 7
    """, (user_id,))
    recent = cursor.fetchall()

    # Database size
    db_size = os.path.getsize(DB_PATH) / 1024  # KB

    conn.close()

    output = ["# Memory System Statistics\n"]
    output.append(f"**User**: {user_id}")
    output.append(f"**Total Memories**: {total}")
    output.append(f"**Database Size**: {db_size:.1f} KB\n")

    output.append("## By Type")
    for row in by_type:
        output.append(f"- {row['memory_type'] or 'untyped'}: {row['count']}")

    output.append("\n## By Project (Top 10)")
    for row in by_project:
        output.append(f"- {row['project']}: {row['count']}")

    output.append("\n## Recent Activity (Last 7 Days)")
    for row in recent:
        output.append(f"- {row['date']}: {row['count']} memories")

    return '\n'.join(output)


@mcp.tool()
def memory_summarize_session(
    project: str,
    summary: str,
    key_outcomes: list[str] = None,
    decisions_made: list[str] = None,
    problems_solved: list[str] = None,
    open_questions: list[str] = None,
    next_steps: list[str] = None
) -> str:
    """
    Summarize a work session. Call this at the end of significant sessions to capture value.

    Args:
        project: Project name
        summary: Brief overall summary of what was accomplished
        key_outcomes: List of main things achieved
        decisions_made: Important decisions and their reasoning
        problems_solved: Issues encountered and how they were resolved
        open_questions: Unresolved questions for future sessions
        next_steps: Concrete next actions to take

    Returns:
        Confirmation with session summary ID
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Build structured content
    content_parts = [f"## Session Summary\n{summary}\n"]

    if key_outcomes:
        content_parts.append("### Key Outcomes")
        for outcome in key_outcomes:
            content_parts.append(f"- {outcome}")
        content_parts.append("")

    if decisions_made:
        content_parts.append("### Decisions Made")
        for decision in decisions_made:
            content_parts.append(f"- {decision}")
        content_parts.append("")

    if problems_solved:
        content_parts.append("### Problems Solved")
        for problem in problems_solved:
            content_parts.append(f"- {problem}")
        content_parts.append("")

    if open_questions:
        content_parts.append("### Open Questions")
        for question in open_questions:
            content_parts.append(f"- {question}")
        content_parts.append("")

    if next_steps:
        content_parts.append("### Next Steps")
        for step in next_steps:
            content_parts.append(f"- {step}")

    full_content = '\n'.join(content_parts)

    # Store as high-importance session summary
    cursor.execute("""
        INSERT INTO memories (content, summary, project, tags, importance, memory_type, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (full_content, summary[:200], project, json.dumps(["session-summary"]), 9, "context", user_id))

    session_id = cursor.lastrowid

    # Also store individual decisions as separate high-importance memories
    if decisions_made:
        for decision in decisions_made:
            cursor.execute("""
                INSERT INTO memories (content, project, tags, importance, memory_type, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (decision, project, json.dumps(["from-session", str(session_id)]), 8, "decision", user_id))

    # Update project last accessed
    cursor.execute("""
        INSERT INTO projects (name, last_accessed, user_id)
        VALUES (?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(name, user_id) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
    """, (project, user_id))

    conn.commit()
    conn.close()

    return f"Session summary stored (ID: {session_id}) with {len(decisions_made or [])} decisions, {len(next_steps or [])} next steps"


@mcp.tool()
def memory_store_correction(
    what_claude_said: str,
    what_was_wrong: str,
    correct_approach: str,
    project: str = None,
    category: str = None
) -> str:
    """
    Store a correction when Claude makes a mistake. These are HIGH PRIORITY memories
    that help prevent future errors.

    Args:
        what_claude_said: What Claude incorrectly stated or did
        what_was_wrong: Why it was wrong
        correct_approach: The right way to handle this
        project: Related project (optional)
        category: Category like "code", "architecture", "workflow", "preferences"

    Returns:
        Confirmation with correction ID
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    # Build correction content
    content = f"""## Correction Record

### What Claude Said/Did (WRONG):
{what_claude_said}

### Why It Was Wrong:
{what_was_wrong}

### Correct Approach:
{correct_approach}

**Category**: {category or 'general'}
"""

    tags = ["correction", "high-priority"]
    if category:
        tags.append(category)

    # Store with maximum importance - corrections are critical
    cursor.execute("""
        INSERT INTO memories (content, summary, project, tags, importance, memory_type, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        content,
        f"CORRECTION: {what_was_wrong[:100]}",
        project,
        json.dumps(tags),
        10,  # Maximum importance
        "error",  # Using error type for corrections
        user_id
    ))

    correction_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return f"Correction stored (ID: {correction_id}) - This will be prioritized in future context loading"


@mcp.tool()
def memory_get_corrections(
    project: str = None,
    category: str = None,
    limit: int = 10
) -> str:
    """
    Retrieve stored corrections to review past mistakes and learnings.

    Args:
        project: Filter by project
        category: Filter by category (code, architecture, workflow, preferences)
        limit: Maximum results

    Returns:
        List of corrections
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    sql = """
        SELECT id, content, project, tags, created_at
        FROM memories
        WHERE memory_type = 'error'
        AND tags LIKE '%correction%'
        AND user_id = ?
    """
    params = [user_id]

    if project:
        sql += " AND project = ?"
        params.append(project)

    if category:
        sql += " AND tags LIKE ?"
        params.append(f'%{category}%')

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()

    if not results:
        return "No corrections found"

    output = [f"# Stored Corrections ({len(results)} found)\n"]

    for row in results:
        output.append(f"---\n**ID {row['id']}** | Project: {row['project'] or 'general'} | {row['created_at']}\n")
        output.append(row['content'])
        output.append("")

    return '\n'.join(output)


@mcp.tool()
def memory_smart_context(
    current_directory: str = None,
    include_corrections: bool = True,
    include_recent: bool = True,
    include_unfinished: bool = True
) -> str:
    """
    Intelligently load context based on current situation. Use this at session start.

    Args:
        current_directory: Current working directory to detect project
        include_corrections: Include recent corrections (highly recommended)
        include_recent: Include recent memories
        include_unfinished: Include sessions with open questions/next steps

    Returns:
        Smart context tailored to current situation
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    output = ["# Smart Context Load\n"]

    # Detect project from directory
    detected_project = None
    if current_directory:
        # Try to match directory to known projects
        cursor.execute("SELECT name FROM projects WHERE user_id = ? ORDER BY last_accessed DESC", (user_id,))
        projects = cursor.fetchall()
        for proj in projects:
            if proj['name'] and proj['name'] in current_directory:
                detected_project = proj['name']
                break

        if detected_project:
            output.append(f"**Detected Project**: {detected_project}\n")

    # Always load corrections first - they're most important
    if include_corrections:
        cursor.execute("""
            SELECT content, created_at FROM memories
            WHERE memory_type = 'error' AND tags LIKE '%correction%' AND user_id = ?
            ORDER BY created_at DESC LIMIT 5
        """, (user_id,))
        corrections = cursor.fetchall()

        if corrections:
            output.append("## ⚠️ Recent Corrections (Review These!)\n")
            for corr in corrections:
                output.append(f"**{corr['created_at']}**")
                # Extract just the key points
                lines = corr['content'].split('\n')
                for line in lines:
                    if line.startswith('### Correct Approach:'):
                        idx = lines.index(line)
                        if idx + 1 < len(lines):
                            output.append(f"✓ {lines[idx + 1]}")
                        break
            output.append("")

    # Load unfinished work (sessions with next steps)
    if include_unfinished:
        cursor.execute("""
            SELECT content, project, created_at FROM memories
            WHERE memory_type = 'context'
            AND tags LIKE '%session-summary%'
            AND content LIKE '%### Next Steps%'
            AND user_id = ?
            ORDER BY created_at DESC LIMIT 3
        """, (user_id,))
        unfinished = cursor.fetchall()

        if unfinished:
            output.append("## 📋 Unfinished Work\n")
            for item in unfinished:
                output.append(f"**{item['project'] or 'General'}** ({item['created_at']})")
                # Extract next steps
                if '### Next Steps' in item['content']:
                    steps_section = item['content'].split('### Next Steps')[1]
                    steps = [s.strip() for s in steps_section.split('\n') if s.strip().startswith('-')]
                    for step in steps[:3]:
                        output.append(f"  {step}")
            output.append("")

    # Load recent high-importance memories
    if include_recent:
        params = [user_id]
        sql = """
            SELECT content, project, memory_type, importance, created_at
            FROM memories
            WHERE importance >= 7 AND user_id = ?
        """
        if detected_project:
            sql += " AND project = ?"
            params.append(detected_project)
        sql += " ORDER BY created_at DESC LIMIT 5"

        cursor.execute(sql, params)
        recent = cursor.fetchall()

        if recent:
            output.append("## 🔥 Recent Important Items\n")
            for item in recent:
                output.append(f"- [{item['memory_type']}] {item['content'][:150]}...")
            output.append("")

    conn.close()

    if len(output) == 1:
        output.append("No relevant context found. This appears to be a fresh start.")

    return '\n'.join(output)


@mcp.tool()
def memory_find_patterns(
    pattern_type: str = "all",
    project: str = None,
    time_range_days: int = 30
) -> str:
    """
    Analyze memories to find recurring patterns. Use this to learn from history.

    Args:
        pattern_type: Type of patterns to find:
            - "errors": Recurring errors and how they were solved
            - "decisions": Common decision patterns
            - "workflows": Repeated workflows
            - "all": All patterns
        project: Filter by project
        time_range_days: How far back to look

    Returns:
        Analysis of patterns found in memories
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation
    user_id = get_current_user()

    output = [f"# Pattern Analysis ({pattern_type})\n"]

    # Find correction patterns (recurring errors)
    if pattern_type in ["errors", "all"]:
        sql = """
            SELECT content, tags, created_at, project
            FROM memories
            WHERE memory_type = 'error'
            AND created_at > datetime('now', ?)
            AND user_id = ?
        """
        params = [f'-{time_range_days} days', user_id]

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += " ORDER BY created_at DESC"
        cursor.execute(sql, params)
        errors = cursor.fetchall()

        if errors:
            output.append(f"## Error Patterns ({len(errors)} found)\n")

            # Group by similar content
            error_groups = {}
            for error in errors:
                # Simple grouping by first 50 chars
                key = error['content'][:50].lower()
                if key not in error_groups:
                    error_groups[key] = []
                error_groups[key].append(error)

            # Find repeated errors
            repeated = [(k, v) for k, v in error_groups.items() if len(v) > 1]
            if repeated:
                output.append("### Recurring Errors (appeared multiple times)")
                for key, group in repeated:
                    output.append(f"- **{len(group)}x**: {group[0]['content'][:200]}...")
                    output.append(f"  Projects: {', '.join(set(e['project'] or 'none' for e in group))}")
                output.append("")

            # Extract correction patterns
            corrections = [e for e in errors if 'correction' in (e['tags'] or '')]
            if corrections:
                output.append("### Learned Corrections")
                for corr in corrections[:5]:
                    if '### Correct Approach:' in corr['content']:
                        approach = corr['content'].split('### Correct Approach:')[1].split('###')[0].strip()
                        output.append(f"- ✓ {approach[:200]}")
                output.append("")

    # Find decision patterns
    if pattern_type in ["decisions", "all"]:
        sql = """
            SELECT content, tags, created_at, project
            FROM memories
            WHERE memory_type = 'decision'
            AND created_at > datetime('now', ?)
            AND user_id = ?
        """
        params = [f'-{time_range_days} days', user_id]

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += " ORDER BY created_at DESC"
        cursor.execute(sql, params)
        decisions = cursor.fetchall()

        if decisions:
            output.append(f"## Decision Patterns ({len(decisions)} found)\n")

            # Group by project
            by_project = {}
            for dec in decisions:
                proj = dec['project'] or 'general'
                if proj not in by_project:
                    by_project[proj] = []
                by_project[proj].append(dec)

            for proj, decs in by_project.items():
                output.append(f"### {proj} ({len(decs)} decisions)")
                for dec in decs[:3]:
                    output.append(f"- {dec['content'][:150]}...")
                output.append("")

    # Find workflow patterns (from session summaries)
    if pattern_type in ["workflows", "all"]:
        sql = """
            SELECT content, project, created_at
            FROM memories
            WHERE tags LIKE '%session-summary%'
            AND created_at > datetime('now', ?)
            AND user_id = ?
        """
        params = [f'-{time_range_days} days', user_id]

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += " ORDER BY created_at DESC"
        cursor.execute(sql, params)
        sessions = cursor.fetchall()

        if sessions:
            output.append(f"## Workflow Patterns ({len(sessions)} sessions)\n")

            # Extract common next steps
            all_next_steps = []
            for session in sessions:
                if '### Next Steps' in session['content']:
                    steps_section = session['content'].split('### Next Steps')[1]
                    steps = [s.strip()[2:] for s in steps_section.split('\n') if s.strip().startswith('-')]
                    all_next_steps.extend(steps)

            # Find common next steps
            if all_next_steps:
                from collections import Counter
                step_counts = Counter(all_next_steps)
                common = step_counts.most_common(5)

                output.append("### Common Next Steps")
                for step, count in common:
                    if count > 1:
                        output.append(f"- **{count}x**: {step}")
                output.append("")

    conn.close()

    if len(output) == 1:
        output.append("No patterns found in the specified time range.")

    return '\n'.join(output)


@mcp.tool()
def memory_compact(
    remove_expired: bool = True,
    remove_low_importance: bool = False,
    min_importance_threshold: int = 3,
    older_than_days: int = 90,
    dry_run: bool = True
) -> str:
    """
    Clean up the memory database by removing expired and low-value memories.

    Args:
        remove_expired: Remove memories past their expires_at timestamp
        remove_low_importance: Remove old, low-importance memories
        min_importance_threshold: Memories below this importance get considered for removal
        older_than_days: Only remove memories older than this many days
        dry_run: If True, only report what would be removed without actually deleting

    Returns:
        Report of memories removed or that would be removed
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation - only compact user's own memories
    user_id = get_current_user()

    output = [f"# Memory Compaction {'(DRY RUN)' if dry_run else 'Report'}\n"]
    output.append(f"**User**: {user_id}\n")
    total_removed = 0

    # Remove expired memories
    if remove_expired:
        cursor.execute("""
            SELECT id, summary, project, expires_at
            FROM memories
            WHERE expires_at IS NOT NULL
            AND expires_at < datetime('now')
            AND user_id = ?
        """, (user_id,))
        expired = cursor.fetchall()

        if expired:
            output.append(f"## Expired Memories: {len(expired)}")
            for mem in expired[:10]:
                output.append(f"- [ID {mem['id']}] {mem['summary'][:50]}... (expired: {mem['expires_at']})")

            if not dry_run:
                cursor.execute("""
                    DELETE FROM memories
                    WHERE expires_at IS NOT NULL
                    AND expires_at < datetime('now')
                    AND user_id = ?
                """, (user_id,))
                total_removed += cursor.rowcount
            output.append("")

    # Remove low-importance old memories
    if remove_low_importance:
        cursor.execute("""
            SELECT id, summary, project, importance, created_at
            FROM memories
            WHERE importance < ?
            AND created_at < datetime('now', ?)
            AND verified = 0
            AND memory_type NOT IN ('correction', 'error')
            AND user_id = ?
        """, (min_importance_threshold, f'-{older_than_days} days', user_id))
        low_importance = cursor.fetchall()

        if low_importance:
            output.append(f"## Low Importance Memories (older than {older_than_days} days): {len(low_importance)}")
            for mem in low_importance[:10]:
                output.append(f"- [ID {mem['id']}] importance={mem['importance']}: {mem['summary'][:50]}...")

            if not dry_run:
                cursor.execute("""
                    DELETE FROM memories
                    WHERE importance < ?
                    AND created_at < datetime('now', ?)
                    AND verified = 0
                    AND memory_type NOT IN ('correction', 'error')
                    AND user_id = ?
                """, (min_importance_threshold, f'-{older_than_days} days', user_id))
                total_removed += cursor.rowcount
            output.append("")

    # Summary
    if dry_run:
        output.append(f"**Would remove {len(expired) if remove_expired else 0} expired + {len(low_importance) if remove_low_importance else 0} low-importance memories**")
        output.append("\nRun with `dry_run=False` to actually remove.")
    else:
        conn.commit()
        output.append(f"**Removed {total_removed} memories**")

    conn.close()
    return '\n'.join(output)


@mcp.tool()
def memory_verify(
    memory_id: int,
    verified: bool = True
) -> str:
    """
    Mark a memory as verified or unverified.

    Args:
        memory_id: ID of the memory to update
        verified: Whether to mark as verified (True) or unverified (False)

    Returns:
        Confirmation message
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current user for isolation - only verify user's own memories
    user_id = get_current_user()

    cursor.execute("""
        UPDATE memories SET verified = ? WHERE id = ? AND user_id = ?
    """, (1 if verified else 0, memory_id, user_id))

    if cursor.rowcount == 0:
        conn.close()
        return f"Memory ID {memory_id} not found (or belongs to another user)"

    conn.commit()
    conn.close()

    return f"Memory ID {memory_id} marked as {'verified' if verified else 'unverified'}"


# ============================================================================
# ENGRAM-ENHANCED TOOLS (Inspired by DeepSeek's Engram architecture)
# ============================================================================

# Lazy load Engram to avoid slow startup
_engram = None

def get_engram():
    """Lazy load the Engram enhancement module."""
    global _engram
    if _engram is None:
        try:
            from engram import EngramMemory, EngramConfig
            config = EngramConfig(
                hash_cache_max_size=10000,
                hash_cache_ttl_seconds=3600,
                hot_cache_min_importance=9,
                gating_threshold=0.3
            )
            _engram = EngramMemory(DB_PATH, config)
        except Exception as e:
            print(f"Warning: Could not load Engram module: {e}")
            return None
    return _engram


@mcp.tool()
def memory_recall_fast(
    query: str,
    project: str = None,
    limit: int = 10
) -> str:
    """
    Enhanced recall with O(1) hash cache for repeated queries.

    Uses Engram-style optimizations:
    - Hash-based fast path for repeated queries
    - Hot cache for corrections and high-importance memories
    - Tokenizer compression for consistent matching

    Args:
        query: Search query
        project: Filter by project name
        limit: Maximum results to return

    Returns:
        Matching memories with cache hit/miss info
    """
    engram = get_engram()

    if engram is None:
        # Fallback to standard recall
        return memory_recall(query, project, "context", limit, 1)

    result = engram.recall(query, project, limit)

    output = ["# Memory Recall (Engram Enhanced)\n"]
    output.append(f"**Source**: {result['source']} | **Compressed Query**: {result['compressed_query']}\n")

    if not result['results']:
        output.append(f"No memories found matching '{query}'")
        return '\n'.join(output)

    output.append(f"Found {len(result['results'])} memories:\n")

    for mem in result['results']:
        source_tag = f" [{mem.get('source', 'db')}]" if mem.get('source') == 'hot_cache' else ""
        output.append(f"""
---
**ID {mem['id']}**{source_tag} | {mem.get('memory_type', 'context')} | Importance: {mem.get('importance', 5)}/10
Project: {mem.get('project') or 'none'}

{mem['content'][:500]}{'...' if len(mem['content']) > 500 else ''}
""")

    return '\n'.join(output)


@mcp.tool()
def memory_corrections_instant() -> str:
    """
    O(1) instant access to corrections from hot cache.

    Corrections are pre-loaded in memory for immediate retrieval.
    Use this at session start to quickly load critical corrections.

    Returns:
        Top corrections from hot cache
    """
    engram = get_engram()

    if engram is None:
        # Fallback to standard corrections
        return memory_get_corrections(None, None, 10)

    corrections = engram.get_corrections(10)

    if not corrections:
        return "No corrections in hot cache"

    output = ["# Corrections (Hot Cache - O(1) Access)\n"]
    output.append(f"Loaded {len(corrections)} critical corrections:\n")

    for corr in corrections:
        output.append(f"""
---
**ID {corr.id}** | Project: {corr.project or 'general'} | Importance: {corr.importance}/10

{corr.content[:400]}{'...' if len(corr.content) > 400 else ''}
""")

    return '\n'.join(output)


@mcp.tool()
def memory_engram_stats() -> str:
    """
    Get Engram enhancement statistics.

    Shows:
    - Hash cache hit rate and size
    - Hot cache loaded memories
    - Configuration settings

    Returns:
        Detailed Engram statistics
    """
    engram = get_engram()

    if engram is None:
        return "Engram module not loaded"

    stats = engram.get_stats()

    output = ["# Engram Enhancement Statistics\n"]

    # Hash cache stats
    hc = stats['hash_cache']
    output.append("## Hash Cache (O(1) Fast Path)")
    output.append(f"- **Size**: {hc['size']} entries")
    output.append(f"- **Hit Rate**: {hc['hit_rate']}")
    output.append(f"- **Hits**: {hc['hits']} | **Misses**: {hc['misses']}")
    output.append(f"- **Evictions**: {hc['evictions']}\n")

    # Hot cache stats
    hot = stats['hot_cache']
    output.append("## Hot Cache (Pre-loaded Critical Memories)")
    output.append(f"- **Total Memories**: {hot['total_memories']}")
    output.append(f"- **Corrections**: {hot['corrections']}")
    output.append(f"- **Projects**: {hot['projects']}")
    output.append(f"- **Last Refresh**: {hot['last_refresh']}\n")

    # Config
    cfg = stats['config']
    output.append("## Configuration")
    output.append(f"- **Max Cache Size**: {cfg['hash_cache_max_size']}")
    output.append(f"- **Cache TTL**: {cfg['hash_cache_ttl_seconds']}s")
    output.append(f"- **Gating Threshold**: {cfg['gating_threshold']}")
    output.append(f"- **Memory Allocation Ratio**: {cfg['memory_allocation_ratio']} (25% of context)")

    return '\n'.join(output)


@mcp.tool()
def memory_invalidate_cache() -> str:
    """
    Invalidate Engram caches after manual data changes.

    Call this after directly modifying the database or when
    you want to force a cache refresh.

    Returns:
        Confirmation message
    """
    engram = get_engram()

    if engram is None:
        return "Engram module not loaded"

    engram.invalidate_cache()

    return "Engram caches invalidated. Hash cache cleared, hot cache refreshed."


@mcp.tool()
def memory_smart_recall(
    query: str,
    current_context: str = None,
    project: str = None,
    limit: int = 10
) -> str:
    """
    Context-aware memory recall with gating.

    Uses Engram's context-aware gating to filter out irrelevant memories.
    Memories that don't match the current context are suppressed.

    Args:
        query: Search query
        current_context: Description of current task/context for relevance filtering
        project: Filter by project name
        limit: Maximum results to return

    Returns:
        Relevant memories filtered by context, with relevance scores
    """
    engram = get_engram()

    if engram is None:
        return memory_recall(query, project, "context", limit, 1)

    # Generate context embedding if context provided
    context_embedding = None
    if current_context:
        context_embedding = generate_embedding(current_context)
        if context_embedding:
            context_embedding = np.frombuffer(context_embedding, dtype=np.float32)

    # Get gated results
    gated_results = engram.recall_gated(query, context_embedding, project, limit)

    if not gated_results:
        return f"No memories found matching '{query}' with sufficient relevance to current context"

    output = ["# Smart Recall (Context-Gated)\n"]
    if current_context:
        output.append(f"**Context**: {current_context[:100]}...\n")
    output.append(f"Found {len(gated_results)} relevant memories:\n")

    for mem, relevance in gated_results:
        output.append(f"""
---
**ID {mem['id']}** | Relevance: {relevance:.1%} | {mem.get('memory_type', 'context')}
Project: {mem.get('project') or 'none'} | Importance: {mem.get('importance', 5)}/10

{mem['content'][:400]}{'...' if len(mem['content']) > 400 else ''}
""")

    return '\n'.join(output)


# Hook into memory_store to invalidate cache
_original_memory_store = memory_store.__wrapped__ if hasattr(memory_store, '__wrapped__') else None

@mcp.tool()
def memory_store_enhanced(
    content: str,
    project: str = None,
    tags: list[str] = None,
    importance: int = 5,
    memory_type: str = "context",
    summary: str = None,
    namespace: str = "global",
    verified: bool = False,
    expires_at: str = None,
    source: str = "manual"
) -> str:
    """
    Store a new memory with automatic cache invalidation.

    Same as memory_store but also invalidates Engram caches
    to ensure consistency.

    Args:
        content: The full content of the memory
        project: Project name this memory relates to
        tags: List of tags for categorization
        importance: 1-10 scale (10 = critical)
        memory_type: One of: decision, fact, preference, context, outcome, error
        summary: Brief summary (auto-generated if not provided)
        namespace: Scope isolation (global | project:<name> | machine | revit)
        verified: Whether this memory has been verified as accurate
        expires_at: Optional ISO8601 timestamp for automatic expiration
        source: Origin of memory (manual | auto | tool)

    Returns:
        Confirmation with memory ID
    """
    # Store using original function
    result = memory_store(content, project, tags, importance, memory_type,
                         summary, namespace, verified, expires_at, source)

    # Invalidate cache if high importance (will appear in hot cache)
    if importance >= 9:
        engram = get_engram()
        if engram:
            engram.invalidate_cache()

    return result


# ============================================================================
# SELF-IMPROVEMENT LOOP TOOLS
# ============================================================================

# Patterns that indicate user is correcting Claude
CORRECTION_PATTERNS = [
    "no that's wrong", "that's incorrect", "actually,", "no, i meant",
    "i told you", "not what i", "you forgot", "that's not right",
    "wrong approach", "you should have", "the correct way", "mistake",
    "you misunderstood", "let me clarify", "that's not how", "don't do that"
]


def detect_correction_intent(user_message: str) -> bool:
    """
    Detect if a user message indicates they're correcting Claude.

    Args:
        user_message: The user's message text

    Returns:
        True if correction intent detected
    """
    message_lower = user_message.lower()
    return any(pattern in message_lower for pattern in CORRECTION_PATTERNS)


@mcp.tool()
def memory_check_before_action(
    planned_action: str,
    action_context: str = None
) -> str:
    """
    Check if any stored correction applies before taking an action.
    Call this BEFORE major actions to avoid repeating known mistakes.

    Args:
        planned_action: Description of what Claude is about to do
        action_context: Additional context about the situation

    Returns:
        Warning if relevant correction found, or clearance to proceed
    """
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_current_user()

    # Get all corrections for this user
    cursor.execute("""
        SELECT id, content, project, created_at, times_surfaced, times_helped
        FROM memories
        WHERE memory_type = 'error'
        AND tags LIKE '%correction%'
        AND user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))

    corrections = cursor.fetchall()

    if not corrections:
        conn.close()
        return "No corrections on file. Proceed with action."

    # Check each correction for relevance using keyword matching
    planned_lower = planned_action.lower()
    context_lower = (action_context or "").lower()
    combined = f"{planned_lower} {context_lower}"

    relevant_corrections = []

    for corr in corrections:
        content_lower = corr['content'].lower()

        # Extract key terms from correction
        # Look for overlap in significant words
        corr_words = set(w for w in content_lower.split() if len(w) > 4)
        action_words = set(w for w in combined.split() if len(w) > 4)

        overlap = corr_words & action_words

        if len(overlap) >= 3:  # At least 3 significant words match
            relevant_corrections.append((corr, len(overlap)))

            # Increment times_surfaced
            cursor.execute("""
                UPDATE memories
                SET times_surfaced = times_surfaced + 1,
                    last_tested = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (corr['id'],))

    conn.commit()
    conn.close()

    if not relevant_corrections:
        return "No relevant corrections found. Proceed with action."

    # Sort by relevance (overlap count)
    relevant_corrections.sort(key=lambda x: x[1], reverse=True)

    output = ["# ⚠️ RELEVANT CORRECTIONS FOUND\n"]
    output.append("**Review before proceeding:**\n")

    for corr, overlap_count in relevant_corrections[:3]:  # Top 3
        output.append("---")
        output.append(f"**Correction ID {corr['id']}** (relevance: {overlap_count} keywords)")
        output.append(f"Project: {corr['project'] or 'general'}")
        output.append(f"Surfaced {corr['times_surfaced']} times, helped {corr['times_helped']} times")
        output.append(f"\n{corr['content'][:500]}...")
        output.append("")

    output.append("\n**Action:** Review corrections above. If they apply, adjust approach.")
    output.append("If proceeding anyway, call `memory_correction_helped(id, False)` if it causes issues.")

    return '\n'.join(output)


@mcp.tool()
def memory_correction_helped(
    correction_id: int,
    helped: bool,
    notes: str = None
) -> str:
    """
    Record whether a surfaced correction actually helped avoid a mistake.
    This feedback improves the self-improvement loop.

    Args:
        correction_id: ID of the correction that was surfaced
        helped: True if the correction prevented a mistake, False if not relevant
        notes: Optional notes about why it helped or didn't

    Returns:
        Confirmation and updated effectiveness score
    """
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_current_user()

    # Verify correction exists and belongs to user
    cursor.execute("""
        SELECT times_surfaced, times_helped, effectiveness_score
        FROM memories
        WHERE id = ? AND user_id = ? AND memory_type = 'error'
    """, (correction_id, user_id))

    result = cursor.fetchone()
    if not result:
        conn.close()
        return f"Correction {correction_id} not found"

    times_surfaced = result['times_surfaced'] or 1
    times_helped = (result['times_helped'] or 0) + (1 if helped else 0)

    # Calculate new effectiveness score
    effectiveness = times_helped / max(times_surfaced, 1)

    cursor.execute("""
        UPDATE memories
        SET times_helped = ?,
            effectiveness_score = ?,
            last_tested = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (times_helped, effectiveness, correction_id))

    # If notes provided, append to content
    if notes:
        cursor.execute("SELECT content FROM memories WHERE id = ?", (correction_id,))
        current_content = cursor.fetchone()['content']
        timestamp = datetime.now().isoformat()
        updated_content = f"{current_content}\n\n---\n**Feedback ({timestamp})**: {'Helped' if helped else 'Not relevant'} - {notes}"
        cursor.execute("UPDATE memories SET content = ? WHERE id = ?", (updated_content, correction_id))

    conn.commit()
    conn.close()

    return f"Correction {correction_id} feedback recorded. Effectiveness: {effectiveness:.0%} ({times_helped}/{times_surfaced})"


@mcp.tool()
def memory_log_avoided_mistake(
    what_almost_happened: str,
    how_avoided: str,
    correction_id: int = None,
    project: str = None
) -> str:
    """
    Log when Claude successfully avoided a known mistake.
    This creates positive reinforcement in the learning loop.

    Args:
        what_almost_happened: The mistake that was almost made
        how_avoided: How the mistake was caught/avoided
        correction_id: ID of correction that helped (if any)
        project: Related project

    Returns:
        Confirmation of success logging
    """
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_current_user()

    # Build success record
    content = f"""## Mistake Avoided (Success Log)

### What Almost Happened:
{what_almost_happened}

### How It Was Avoided:
{how_avoided}

### Related Correction ID: {correction_id or 'None'}
"""

    tags = ["success-log", "avoided-mistake", "self-improvement"]

    cursor.execute("""
        INSERT INTO memories (content, summary, project, tags, importance, memory_type, user_id, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        content,
        f"AVOIDED: {what_almost_happened[:100]}",
        project,
        json.dumps(tags),
        7,  # High importance for successes
        "outcome",
        user_id,
        "auto"
    ))

    success_id = cursor.lastrowid

    # If correction_id provided, mark it as helped and link
    if correction_id:
        cursor.execute("""
            UPDATE memories
            SET times_helped = times_helped + 1,
                effectiveness_score = CAST(times_helped + 1 AS REAL) / MAX(times_surfaced, 1),
                last_tested = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (correction_id, user_id))

        # Create relationship link
        try:
            cursor.execute("""
                INSERT INTO memory_relationships (source_id, target_id, relationship_type, notes)
                VALUES (?, ?, 'supports', 'Success resulted from this correction')
            """, (success_id, correction_id))
        except Exception:
            pass  # Relationship may already exist

    conn.commit()
    conn.close()

    return f"Success logged (ID: {success_id}). Learning loop reinforced!"


@mcp.tool()
def memory_auto_capture_correction(
    user_message: str,
    claude_mistake: str,
    correct_approach: str,
    project: str = None
) -> str:
    """
    Automatically capture a correction detected from conversation.
    Called when correction intent is detected in user message.

    Args:
        user_message: The user's corrective message
        claude_mistake: What Claude did wrong
        correct_approach: The right way to handle it
        project: Related project

    Returns:
        Confirmation of auto-captured correction
    """
    # Delegate to existing correction storage
    return memory_store_correction(
        what_claude_said=claude_mistake,
        what_was_wrong=f"User correction: {user_message}",
        correct_approach=correct_approach,
        project=project,
        category="auto-detected"
    )


@mcp.tool()
def memory_synthesize_patterns() -> str:
    """
    Analyze all corrections to find root causes and patterns.
    Generates meta-learnings from accumulated mistakes.

    Returns:
        Analysis of correction patterns with recommendations
    """
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_current_user()

    # Get all corrections
    cursor.execute("""
        SELECT id, content, project, tags, created_at,
               times_surfaced, times_helped, effectiveness_score
        FROM memories
        WHERE memory_type = 'error'
        AND tags LIKE '%correction%'
        AND user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))

    corrections = cursor.fetchall()
    conn.close()

    if not corrections:
        return "No corrections found to analyze."

    output = ["# Correction Pattern Analysis\n"]
    output.append(f"**Total Corrections:** {len(corrections)}\n")

    # Analyze by category
    categories = {}
    projects = {}
    effective = []
    ineffective = []

    for corr in corrections:
        # Parse tags
        tags = json.loads(corr['tags']) if corr['tags'] else []
        for tag in tags:
            if tag not in ['correction', 'high-priority']:
                categories[tag] = categories.get(tag, 0) + 1

        # Track by project
        proj = corr['project'] or 'general'
        projects[proj] = projects.get(proj, 0) + 1

        # Track effectiveness
        eff = corr['effectiveness_score'] or 0
        if eff > 0.5:
            effective.append(corr)
        elif corr['times_surfaced'] and corr['times_surfaced'] > 2 and eff < 0.3:
            ineffective.append(corr)

    # Category breakdown
    if categories:
        output.append("## By Category")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            output.append(f"- **{cat}**: {count} corrections")
        output.append("")

    # Project breakdown
    output.append("## By Project")
    for proj, count in sorted(projects.items(), key=lambda x: -x[1])[:5]:
        output.append(f"- **{proj}**: {count} corrections")
    output.append("")

    # Effectiveness insights
    output.append("## Effectiveness Analysis")
    output.append(f"- **Effective corrections (>50% help rate):** {len(effective)}")
    output.append(f"- **Potentially outdated (<30% help rate, surfaced 3+ times):** {len(ineffective)}")
    output.append("")

    # Pattern detection - look for common words
    all_content = ' '.join(c['content'].lower() for c in corrections)
    words = all_content.split()

    # Find action words that appear frequently
    action_words = ['guess', 'assume', 'skip', 'forget', 'ignore', 'wrong',
                    'incorrect', 'miss', 'overlook', 'confuse']
    word_freq = {}
    for word in action_words:
        count = words.count(word)
        if count > 0:
            word_freq[word] = count

    if word_freq:
        output.append("## Common Mistake Patterns")
        for word, count in sorted(word_freq.items(), key=lambda x: -x[1]):
            if count >= 2:
                output.append(f"- Claude tends to **{word}** things ({count} mentions)")
        output.append("")

    # Recommendations
    output.append("## Recommendations")

    if 'workflow' in categories and categories['workflow'] > 3:
        output.append("- **Process Issue**: Many workflow corrections. Consider creating checklists.")

    if 'code' in categories and categories['code'] > 3:
        output.append("- **Code Quality**: Multiple code corrections. Run more pre-action checks.")

    if ineffective:
        output.append(f"- **Cleanup**: {len(ineffective)} corrections may be outdated. Review and archive.")

    if len(corrections) > 20:
        output.append("- **Pattern**: Large correction history. Consider generating meta-corrections.")

    return '\n'.join(output)


@mcp.tool()
def memory_get_improvement_stats() -> str:
    """
    Get statistics on the self-improvement loop performance.

    Returns:
        Metrics on learning effectiveness
    """
    conn = get_db()
    cursor = conn.cursor()

    user_id = get_current_user()

    # Correction stats
    cursor.execute("""
        SELECT
            COUNT(*) as total_corrections,
            SUM(times_surfaced) as total_surfaced,
            SUM(times_helped) as total_helped,
            AVG(effectiveness_score) as avg_effectiveness
        FROM memories
        WHERE memory_type = 'error'
        AND tags LIKE '%correction%'
        AND user_id = ?
    """, (user_id,))

    corr_stats = cursor.fetchone()

    # Success logs
    cursor.execute("""
        SELECT COUNT(*) as success_count
        FROM memories
        WHERE memory_type = 'outcome'
        AND tags LIKE '%avoided-mistake%'
        AND user_id = ?
    """, (user_id,))

    success_count = cursor.fetchone()['success_count']

    # Recent corrections (last 30 days)
    cursor.execute("""
        SELECT COUNT(*) as recent
        FROM memories
        WHERE memory_type = 'error'
        AND tags LIKE '%correction%'
        AND created_at > datetime('now', '-30 days')
        AND user_id = ?
    """, (user_id,))

    recent = cursor.fetchone()['recent']

    # Corrections with feedback
    cursor.execute("""
        SELECT COUNT(*) as with_feedback
        FROM memories
        WHERE memory_type = 'error'
        AND tags LIKE '%correction%'
        AND times_surfaced > 0
        AND user_id = ?
    """, (user_id,))

    with_feedback = cursor.fetchone()['with_feedback']

    conn.close()

    total = corr_stats['total_corrections'] or 0
    surfaced = corr_stats['total_surfaced'] or 0
    helped = corr_stats['total_helped'] or 0
    avg_eff = corr_stats['avg_effectiveness'] or 0

    output = ["# Self-Improvement Loop Statistics\n"]

    output.append("## Corrections")
    output.append(f"- **Total Corrections:** {total}")
    output.append(f"- **Last 30 Days:** {recent}")
    output.append(f"- **With Feedback:** {with_feedback}")
    output.append("")

    output.append("## Effectiveness")
    output.append(f"- **Times Surfaced:** {surfaced}")
    output.append(f"- **Times Helped:** {helped}")
    output.append(f"- **Average Effectiveness:** {avg_eff:.1%}")
    output.append("")

    output.append("## Positive Reinforcement")
    output.append(f"- **Mistakes Avoided (logged):** {success_count}")
    output.append("")

    # Calculate learning velocity
    if total > 0:
        learning_rate = helped / max(surfaced, 1)
        output.append("## Learning Metrics")
        output.append(f"- **Learning Rate:** {learning_rate:.1%} (corrections that help)")

        if success_count > 0:
            output.append(f"- **Reinforcement Ratio:** {success_count/total:.1f}x (successes per correction)")

    return '\n'.join(output)


@mcp.tool()
def memory_decay_corrections(
    dry_run: bool = True,
    surfaced_threshold: int = 5,
    decay_amount: int = 1
) -> str:
    """
    Decay importance of corrections that aren't helping.

    Corrections that have been surfaced multiple times but never marked
    as helpful should have their importance reduced over time.

    Args:
        dry_run: If True, only report what would be decayed
        surfaced_threshold: Corrections surfaced this many times with 0 helps get decayed
        decay_amount: How much to reduce importance by

    Returns:
        Report of decayed corrections
    """
    user_id = get_current_user()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find corrections that have been surfaced multiple times but never helped
    cursor.execute("""
        SELECT id, summary, importance, times_surfaced, times_helped, project
        FROM memories
        WHERE user_id = ?
          AND memory_type = 'correction'
          AND times_surfaced >= ?
          AND (times_helped IS NULL OR times_helped = 0)
          AND importance > 1
        ORDER BY times_surfaced DESC
    """, (user_id, surfaced_threshold))

    candidates = cursor.fetchall()

    output = ["# Correction Decay Analysis\n"]

    if not candidates:
        output.append("No corrections need decay. All frequently-surfaced corrections are helping!")
        conn.close()
        return '\n'.join(output)

    output.append(f"**Found {len(candidates)} corrections to decay:**\n")

    decayed = []
    for row in candidates:
        cid, summary, importance, surfaced, helped, project = row
        new_importance = max(1, importance - decay_amount)

        output.append(f"- **ID {cid}** ({project or 'no project'})")
        output.append(f"  - Summary: {(summary or '')[:60]}...")
        output.append(f"  - Surfaced {surfaced}x, helped {helped or 0}x")
        output.append(f"  - Importance: {importance} → {new_importance}")
        output.append("")

        if not dry_run:
            cursor.execute("""
                UPDATE memories
                SET importance = ?
                WHERE id = ?
            """, (new_importance, cid))
            decayed.append(cid)

    if dry_run:
        output.append("---")
        output.append("**Dry run - no changes made.** Call with `dry_run=False` to apply.")
    else:
        conn.commit()
        output.append("---")
        output.append(f"**Decayed {len(decayed)} corrections.**")

    conn.close()
    return '\n'.join(output)


@mcp.tool()
def memory_archive_old_corrections(
    dry_run: bool = True,
    days_old: int = 90,
    max_effectiveness: float = 0.3
) -> str:
    """
    Archive old, low-effectiveness corrections.

    Moves corrections that are old and haven't been effective to an
    'archived' type so they don't clutter active correction checks.

    Args:
        dry_run: If True, only report what would be archived
        days_old: Archive corrections older than this many days
        max_effectiveness: Only archive if effectiveness is below this

    Returns:
        Report of archived corrections
    """
    user_id = get_current_user()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find old, low-effectiveness corrections
    cursor.execute("""
        SELECT id, summary, importance, times_surfaced, effectiveness_score,
               project, created_at
        FROM memories
        WHERE user_id = ?
          AND memory_type = 'correction'
          AND created_at < datetime('now', ?)
          AND (effectiveness_score IS NULL OR effectiveness_score < ?)
          AND times_surfaced > 0
        ORDER BY created_at ASC
    """, (user_id, f'-{days_old} days', max_effectiveness))

    candidates = cursor.fetchall()

    output = ["# Correction Archive Analysis\n"]

    if not candidates:
        output.append("No corrections qualify for archival.")
        output.append(f"(Checked: >{days_old} days old, <{max_effectiveness:.0%} effectiveness)")
        conn.close()
        return '\n'.join(output)

    output.append(f"**Found {len(candidates)} corrections to archive:**\n")

    archived = []
    for row in candidates:
        cid, summary, importance, surfaced, effectiveness, project, created = row

        output.append(f"- **ID {cid}** ({project or 'no project'})")
        output.append(f"  - Created: {created[:10] if created else 'unknown'}")
        output.append(f"  - Summary: {(summary or '')[:60]}...")
        output.append(f"  - Effectiveness: {(effectiveness or 0):.0%}")
        output.append("")

        if not dry_run:
            cursor.execute("""
                UPDATE memories
                SET memory_type = 'archived_correction'
                WHERE id = ?
            """, (cid,))
            archived.append(cid)

    if dry_run:
        output.append("---")
        output.append("**Dry run - no changes made.** Call with `dry_run=False` to apply.")
    else:
        conn.commit()
        output.append("---")
        output.append(f"**Archived {len(archived)} corrections.**")
        output.append("Archived corrections won't appear in correction checks but remain in database.")

    conn.close()
    return '\n'.join(output)


@mcp.tool()
def memory_retire_correction(
    correction_id: int,
    reason: str = "learned"
) -> str:
    """
    Manually retire a correction that has been fully learned.

    Use this when a correction is no longer relevant because:
    - The lesson has been fully internalized
    - The codebase/project has changed
    - The correction was wrong or outdated

    Args:
        correction_id: ID of the correction to retire
        reason: Why retiring (learned, outdated, wrong, not_applicable)

    Returns:
        Confirmation message
    """
    user_id = get_current_user()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Verify correction exists and belongs to user
    cursor.execute("""
        SELECT id, summary, memory_type FROM memories
        WHERE id = ? AND user_id = ?
    """, (correction_id, user_id))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return f"Correction {correction_id} not found or doesn't belong to you."

    if row['memory_type'] != 'correction':
        conn.close()
        return f"Memory {correction_id} is not a correction (type: {row['memory_type']})"

    # Retire the correction
    cursor.execute("""
        UPDATE memories
        SET memory_type = 'retired_correction',
            content = content || '\n\n---\nRetired: ' || datetime('now') || '\nReason: ' || ?
        WHERE id = ?
    """, (reason, correction_id))

    conn.commit()
    conn.close()

    return f"Correction {correction_id} retired (reason: {reason}). It will no longer appear in correction checks."


if __name__ == "__main__":
    mcp.run()

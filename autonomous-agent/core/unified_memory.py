#!/usr/bin/env python3
"""
Unified Memory Interface
========================
Single interface for all memory operations.
Consolidates multiple memory systems into one API.

Provides persistent storage for:
- General memories (context, notes, preferences)
- Corrections (self-improvement loop)
- Patterns (learned behavioral patterns)
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("autonomous-agent.memory")

# ============================================
# CONFIGURATION
# ============================================

# Paths relative to this file's parent (autonomous-agent/)
BASE_DIR = Path(__file__).parent.parent
MEMORY_DB = BASE_DIR / "memory" / "unified.db"

# Ensure directories exist
MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)

# ============================================
# DATABASE SETUP
# ============================================

def init_db():
    """Initialize the unified memory database."""
    conn = sqlite3.connect(str(MEMORY_DB))
    cur = conn.cursor()

    # Main memories table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            tags TEXT,
            importance INTEGER DEFAULT 5,
            project TEXT,
            created_at TEXT NOT NULL,
            accessed_at TEXT,
            access_count INTEGER DEFAULT 0
        )
    """)

    # Corrections table (for self-improvement)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            what_claude_said TEXT NOT NULL,
            what_was_wrong TEXT NOT NULL,
            correct_approach TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            project TEXT,
            effectiveness_score REAL DEFAULT 0,
            times_helped INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Patterns table (for synthesized learnings)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            description TEXT NOT NULL,
            frequency INTEGER DEFAULT 1,
            last_seen TEXT,
            data TEXT
        )
    """)

    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_corrections_category ON corrections(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_corrections_project ON corrections(project)")

    conn.commit()
    conn.close()

# ============================================
# UNIFIED MEMORY CLASS
# ============================================

class UnifiedMemory:
    """
    Single interface for all memory operations.
    Wraps existing memory systems and provides unified access.
    """

    def __init__(self):
        init_db()

    # ==========================================
    # STORE OPERATIONS
    # ==========================================

    def store(self, content: str, category: str = "general",
              tags: List[str] = None, importance: int = 5,
              project: str = None) -> int:
        """Store a memory."""
        conn = sqlite3.connect(str(MEMORY_DB))
        cur = conn.cursor()

        now = datetime.now().isoformat()
        tags_str = ",".join(tags) if tags else ""

        cur.execute("""
            INSERT INTO memories (content, category, tags, importance, project, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (content, category, tags_str, importance, project, now))

        memory_id = cur.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Stored memory #{memory_id}: {content[:50]}...")
        return memory_id

    def store_correction(self, what_claude_said: str, what_was_wrong: str,
                        correct_approach: str, category: str = "general",
                        project: str = None) -> int:
        """Store a correction for self-improvement."""
        conn = sqlite3.connect(str(MEMORY_DB))
        cur = conn.cursor()

        now = datetime.now().isoformat()

        cur.execute("""
            INSERT INTO corrections (what_claude_said, what_was_wrong, correct_approach,
                                    category, project, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (what_claude_said, what_was_wrong, correct_approach, category, project, now))

        correction_id = cur.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Stored correction #{correction_id}: {what_was_wrong[:50]}...")
        return correction_id

    # ==========================================
    # RECALL OPERATIONS
    # ==========================================

    def recall(self, query: str, limit: int = 5,
               category: str = None, project: str = None) -> List[Dict]:
        """Recall memories matching a query."""
        conn = sqlite3.connect(str(MEMORY_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Simple keyword matching (could be enhanced with embeddings)
        sql = "SELECT * FROM memories WHERE content LIKE ?"
        params = [f"%{query}%"]

        if category:
            sql += " AND category = ?"
            params.append(category)

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)

        cur.execute(sql, params)
        rows = cur.fetchall()

        # Update access counts
        for row in rows:
            cur.execute("""
                UPDATE memories SET access_count = access_count + 1, accessed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), row["id"]))

        conn.commit()
        conn.close()

        return [dict(row) for row in rows]

    def get_corrections(self, category: str = None, project: str = None,
                       limit: int = 10) -> List[Dict]:
        """Get recent corrections."""
        conn = sqlite3.connect(str(MEMORY_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        sql = "SELECT * FROM corrections WHERE 1=1"
        params = []

        if category:
            sql += " AND category = ?"
            params.append(category)

        if project:
            sql += " AND project = ?"
            params.append(project)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def check_before_action(self, planned_action: str, context: str = "") -> List[Dict]:
        """
        Check for relevant corrections before taking an action.
        This is the self-improvement loop on the hot path.
        """
        conn = sqlite3.connect(str(MEMORY_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Search for relevant corrections
        keywords = planned_action.lower().split()[:10]  # First 10 words
        relevant = []

        for keyword in keywords:
            if len(keyword) > 3:  # Skip short words
                cur.execute("""
                    SELECT * FROM corrections
                    WHERE what_claude_said LIKE ? OR correct_approach LIKE ?
                    ORDER BY effectiveness_score DESC
                    LIMIT 3
                """, (f"%{keyword}%", f"%{keyword}%"))

                for row in cur.fetchall():
                    if dict(row) not in relevant:
                        relevant.append(dict(row))

        conn.close()

        if relevant:
            logger.info(f"Found {len(relevant)} relevant corrections for planned action")

        return relevant[:5]  # Return top 5

    def log_correction_helped(self, correction_id: int, helped: bool):
        """Log whether a correction helped avoid a mistake."""
        conn = sqlite3.connect(str(MEMORY_DB))
        cur = conn.cursor()

        if helped:
            cur.execute("""
                UPDATE corrections
                SET times_helped = times_helped + 1,
                    effectiveness_score = effectiveness_score + 1
                WHERE id = ?
            """, (correction_id,))
        else:
            cur.execute("""
                UPDATE corrections
                SET effectiveness_score = effectiveness_score - 0.5
                WHERE id = ?
            """, (correction_id,))

        conn.commit()
        conn.close()

    # ==========================================
    # PATTERN OPERATIONS
    # ==========================================

    def store_pattern(self, pattern_type: str, description: str, data: Dict = None):
        """Store a detected pattern."""
        conn = sqlite3.connect(str(MEMORY_DB))
        cur = conn.cursor()

        now = datetime.now().isoformat()
        data_str = json.dumps(data) if data else None

        # Check if pattern exists
        cur.execute("""
            SELECT id, frequency FROM patterns
            WHERE pattern_type = ? AND description = ?
        """, (pattern_type, description))

        row = cur.fetchone()

        if row:
            # Update existing pattern
            cur.execute("""
                UPDATE patterns
                SET frequency = frequency + 1, last_seen = ?, data = ?
                WHERE id = ?
            """, (now, data_str, row[0]))
        else:
            # Insert new pattern
            cur.execute("""
                INSERT INTO patterns (pattern_type, description, last_seen, data)
                VALUES (?, ?, ?, ?)
            """, (pattern_type, description, now, data_str))

        conn.commit()
        conn.close()

    def get_patterns(self, pattern_type: str = None, min_frequency: int = 1) -> List[Dict]:
        """Get stored patterns."""
        conn = sqlite3.connect(str(MEMORY_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        sql = "SELECT * FROM patterns WHERE frequency >= ?"
        params = [min_frequency]

        if pattern_type:
            sql += " AND pattern_type = ?"
            params.append(pattern_type)

        sql += " ORDER BY frequency DESC"

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ==========================================
    # STATISTICS
    # ==========================================

    def get_stats(self) -> Dict:
        """Get memory system statistics."""
        conn = sqlite3.connect(str(MEMORY_DB))
        cur = conn.cursor()

        stats = {}

        cur.execute("SELECT COUNT(*) FROM memories")
        stats["total_memories"] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM corrections")
        stats["total_corrections"] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM patterns")
        stats["total_patterns"] = cur.fetchone()[0]

        cur.execute("SELECT SUM(times_helped) FROM corrections")
        result = cur.fetchone()[0]
        stats["times_corrections_helped"] = result or 0

        cur.execute("SELECT AVG(effectiveness_score) FROM corrections")
        result = cur.fetchone()[0]
        stats["avg_correction_effectiveness"] = round(result, 2) if result else 0

        cur.execute("SELECT category, COUNT(*) FROM memories GROUP BY category")
        stats["memories_by_category"] = dict(cur.fetchall())

        conn.close()
        return stats

    # ==========================================
    # SMART CONTEXT
    # ==========================================

    def get_smart_context(self, current_project: str = None) -> Dict:
        """
        Get intelligent context for session start.
        Returns recent corrections, unfinished work, and relevant memories.
        """
        context = {
            "recent_corrections": self.get_corrections(project=current_project, limit=5),
            "patterns": self.get_patterns(min_frequency=3),
            "stats": self.get_stats()
        }

        # Get high-importance memories for the project
        if current_project:
            conn = sqlite3.connect(str(MEMORY_DB))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute("""
                SELECT * FROM memories
                WHERE project = ? AND importance >= 7
                ORDER BY created_at DESC
                LIMIT 5
            """, (current_project,))

            context["project_memories"] = [dict(row) for row in cur.fetchall()]
            conn.close()

        return context


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

_memory = None

def get_memory() -> UnifiedMemory:
    """Get the singleton memory instance."""
    global _memory
    if _memory is None:
        _memory = UnifiedMemory()
    return _memory

def store(content: str, **kwargs) -> int:
    """Store a memory."""
    return get_memory().store(content, **kwargs)

def recall(query: str, **kwargs) -> List[Dict]:
    """Recall memories."""
    return get_memory().recall(query, **kwargs)

def store_correction(**kwargs) -> int:
    """Store a correction."""
    return get_memory().store_correction(**kwargs)

def check_before_action(planned_action: str, context: str = "") -> List[Dict]:
    """Check for relevant corrections before an action."""
    return get_memory().check_before_action(planned_action, context)


# ============================================
# TEST
# ============================================

if __name__ == "__main__":
    print("Testing Unified Memory...")

    memory = UnifiedMemory()

    # Test store
    mem_id = memory.store(
        "User prefers specific email client configuration",
        category="preferences",
        importance=9
    )
    print(f"Stored memory #{mem_id}")

    # Test correction
    corr_id = memory.store_correction(
        what_claude_said="Used wrong tool for task",
        what_was_wrong="Should have used a different approach",
        correct_approach="Always check user preferences first",
        category="workflow"
    )
    print(f"Stored correction #{corr_id}")

    # Test recall
    results = memory.recall("email")
    print(f"Recalled {len(results)} memories about email")

    # Test check before action
    corrections = memory.check_before_action("open email client")
    print(f"Found {len(corrections)} relevant corrections")

    # Test stats
    stats = memory.get_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")

    print("Unified Memory test complete!")

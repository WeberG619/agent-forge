"""
Common Sense Engine v1.0
========================
Gives any Python-based agent experiential judgment by wrapping
the claude-memory MCP server.

Usage:
    from sense import CommonSense

    cs = CommonSense(project="my-project")

    # Before doing something
    result = cs.before("deploy to /opt/app")
    if result.blocked:
        print(f"STOP: {result.reason}")
    elif result.warnings:
        print(f"CAUTION: {result.warnings}")

    # After something goes wrong
    cs.learn(
        action="deployed to /opt/app",
        what_went_wrong="wrong path, should be /opt/app-v2",
        correct_approach="always check the symlink target first"
    )

    # After catching yourself
    cs.avoided("almost deployed to /opt/app, caught it and used /opt/app-v2")
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

MEMORY_MCP_CMD = None  # Set if using direct MCP calls
SEEDS_PATH = Path(__file__).parent / "seeds.json"
_SEEDS_CACHE = None  # In-memory cache of parsed seeds


@dataclass
class ActionCheck:
    """Result of checking an action against experience."""

    blocked: bool = False
    reason: str = ""
    warnings: list = field(default_factory=list)
    corrections: list = field(default_factory=list)
    confidence: float = 1.0

    @property
    def safe(self) -> bool:
        return not self.blocked and not self.warnings


class CommonSense:
    """
    Experiential judgment engine for agents.

    Wraps the claude-memory MCP server to provide:
    - Pre-action checks against past mistakes
    - Post-action learning from outcomes
    - Seed knowledge from universal patterns
    - Cross-project correction transfer
    """

    def __init__(self, project: str = "general", db_path: Optional[str] = None):
        self.project = project
        self.db_path = db_path or self._find_db()
        self._seeds_loaded = False

    def _find_db(self) -> Optional[str]:
        """Locate the claude-memory SQLite database."""
        candidates = [
            Path.home() / ".claude-memory" / "memories.db",
            Path.home() / ".claude" / "memory.db",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    # ─── PRE-ACTION CHECK ───────────────────────────────────────

    def before(self, action: str, context: str = "") -> ActionCheck:
        """
        Check an action against accumulated experience.

        Call this BEFORE doing anything significant.
        Returns an ActionCheck with go/no-go and any warnings.
        """
        result = ActionCheck()

        # Load seeds on first check
        if not self._seeds_loaded:
            self._ensure_seeds()

        # Classify the action
        classification = self._classify(action)

        # Search for relevant corrections
        corrections = self._recall_corrections(action, context)

        if corrections:
            result.corrections = corrections
            for c in corrections:
                severity = c.get("severity", "medium")
                approach = c.get("correct_approach", c.get("content", ""))
                if severity == "critical":
                    result.blocked = True
                    result.reason = f"BLOCKED by [{c.get('id', 'correction')}]: {approach}"
                    result.confidence = 0.0
                    break
                elif severity == "high":
                    result.warnings.append(f"[HIGH] {approach}")
                    result.confidence = min(result.confidence, 0.3)
                else:
                    result.warnings.append(approach)

        # Apply classification heuristics
        if classification["destructive"] and not corrections:
            result.warnings.append(
                "This looks destructive and has no prior experience. Confirm before proceeding."
            )
            result.confidence = 0.5

        if classification["shared_state"]:
            result.warnings.append("This affects shared state. Verify target.")
            result.confidence = min(result.confidence, 0.7)

        if classification["unfamiliar"]:
            result.confidence = min(result.confidence, 0.6)

        return result

    def _classify(self, action: str) -> dict:
        """Classify an action by risk profile."""
        action_lower = action.lower()

        destructive_signals = [
            "delete",
            "remove",
            "drop",
            "truncate",
            "rm ",
            "rm -",
            "overwrite",
            "force",
            "reset --hard",
            "clean -f",
            "wipe",
            "destroy",
            "purge",
        ]

        shared_signals = [
            "push",
            "deploy",
            "publish",
            "send",
            "email",
            "post",
            "merge",
            "release",
            "broadcast",
            "notify",
        ]

        return {
            "destructive": any(s in action_lower for s in destructive_signals),
            "shared_state": any(s in action_lower for s in shared_signals),
            "unfamiliar": not self._has_precedent(action),
            "reversible": not any(s in action_lower for s in destructive_signals + shared_signals),
        }

    def _has_precedent(self, action: str) -> bool:
        """Check if we've done something like this before successfully."""
        try:
            results = self._memory_search(action, memory_type="context")
            return len(results) > 0
        except Exception:
            return False

    # ─── POST-ACTION LEARNING ──────────────────────────────────

    def learn(
        self,
        action: str,
        what_went_wrong: str,
        correct_approach: str,
        category: str = "execution",
        severity: str = "medium",
        tags: Optional[list] = None,
    ):
        """
        Store a correction from a mistake or user feedback.

        This is the primary learning mechanism. Every call makes the
        agent smarter for next time.
        """
        correction = {
            "what_claude_said": action,
            "what_was_wrong": what_went_wrong,
            "correct_approach": correct_approach,
            "project": self.project,
            "category": category,
        }

        # Store via MCP if available
        stored = self._store_correction(correction)

        # Also store as searchable memory with tags
        content = (
            f"CORRECTION [{severity.upper()}]: {action}\n"
            f"Wrong: {what_went_wrong}\n"
            f"Right: {correct_approach}\n"
            f"Domain: {category}"
        )

        all_tags = ["correction", "common-sense", category, severity]
        if tags:
            all_tags.extend(tags)

        self._store_memory(
            content, tags=all_tags, importance=self._severity_to_importance(severity)
        )

        return stored

    def avoided(self, description: str):
        """Log that a known mistake was successfully avoided."""
        content = f"AVOIDED MISTAKE: {description}"
        self._store_memory(
            content, tags=["avoided-mistake", "common-sense", "positive"], importance=5
        )

    def succeeded(self, action: str, context: str = ""):
        """Log a successful action as a known-good pattern."""
        content = f"KNOWN GOOD: {action}"
        if context:
            content += f"\nContext: {context}"
        self._store_memory(content, tags=["known-good", "common-sense", "positive"], importance=4)

    # ─── SEED MANAGEMENT ───────────────────────────────────────

    def _ensure_seeds(self):
        """Load seed corrections into the in-memory cache (no DB write on every run)."""
        global _SEEDS_CACHE
        if _SEEDS_CACHE is not None:
            self._seeds_loaded = True
            return

        if SEEDS_PATH.exists():
            with open(SEEDS_PATH) as f:
                _SEEDS_CACHE = json.load(f).get("corrections", [])
        else:
            _SEEDS_CACHE = []

        self._seeds_loaded = True

    def seed(self, seeds_path: Optional[str] = None):
        """
        Load pre-built corrections into memory.
        Call once to bootstrap common sense from universal patterns.
        """
        path = Path(seeds_path) if seeds_path else SEEDS_PATH
        if not path.exists():
            print(f"Seeds file not found: {path}")
            return 0

        with open(path) as f:
            data = json.load(f)

        count = 0
        for correction in data.get("corrections", []):
            content = (
                f"SEED CORRECTION [{correction['id']}]: {correction['domain']}\n"
                f"What goes wrong: {correction['what_went_wrong']}\n"
                f"Correct approach: {correction['correct_approach']}\n"
                f"Detection: {correction['detection']}"
            )

            tags = ["seed", "common-sense", "correction"] + correction.get("tags", [])
            importance = self._severity_to_importance(correction.get("severity", "medium"))

            self._store_memory(content, tags=tags, importance=importance)
            count += 1

        print(f"Seeded {count} corrections")
        return count

    # ─── PATTERN SYNTHESIS ─────────────────────────────────────

    def synthesize(self) -> list:
        """
        Analyze accumulated corrections for patterns.
        Returns clusters of related corrections that suggest
        deeper behavioral issues.
        """
        corrections = self._memory_search("CORRECTION", memory_type="correction")

        # Group by domain
        domains = {}
        for c in corrections:
            content = c.get("content", "")
            for domain in [
                "filesystem",
                "git",
                "network",
                "execution",
                "scope",
                "deployment",
                "data",
                "identity",
            ]:
                if domain in content.lower():
                    domains.setdefault(domain, []).append(content)
                    break

        patterns = []
        for domain, items in domains.items():
            if len(items) >= 2:
                patterns.append(
                    {
                        "domain": domain,
                        "count": len(items),
                        "insight": f"Recurring issues in {domain} ({len(items)} corrections). Review and consider adding a pre-check.",
                        "items": items[:5],  # Cap for readability
                    }
                )

        return sorted(patterns, key=lambda p: p["count"], reverse=True)

    # ─── INTERNALS ─────────────────────────────────────────────

    def _recall_corrections(self, action: str, context: str = "") -> list:
        """
        Search for corrections relevant to this action.
        Uses three strategies:
        1. Direct seed matching (fast, no DB needed)
        2. Keyword-decomposed DB search
        3. Full-text fallback
        """
        results = []

        # Strategy 1: Match directly against seed detection patterns
        seed_matches = self._match_seeds(action)
        results.extend(seed_matches)

        # Strategy 2: Keyword-decomposed DB search
        query = f"{action} {context}".strip()
        try:
            db_results = self._keyword_search(query, memory_type="correction")
            # Deduplicate against seed matches
            seen = {r.get("id", r.get("correct_approach", "")) for r in results}
            for r in db_results:
                key = r.get("id", r.get("correct_approach", r.get("content", "")))
                if key not in seen:
                    results.append(r)
                    seen.add(key)
        except Exception:
            pass

        return results

    def _match_seeds(self, action: str) -> list:
        """Match an action directly against seed detection patterns. No DB needed."""
        global _SEEDS_CACHE

        if _SEEDS_CACHE is None:
            if SEEDS_PATH.exists():
                with open(SEEDS_PATH) as f:
                    _SEEDS_CACHE = json.load(f).get("corrections", [])
            else:
                _SEEDS_CACHE = []

        action_lower = action.lower()
        action_words = set(action_lower.split())
        matches = []

        for seed in _SEEDS_CACHE:
            detection = seed.get("detection", "").lower()
            # Check detection keywords against action
            detection_words = set(detection.replace(",", " ").replace("/", " ").split())
            overlap = action_words & detection_words
            # Also check for substring matches (phrases like "rm -rf")
            phrase_match = any(
                phrase.strip() in action_lower
                for phrase in detection.split(",")
                if len(phrase.strip()) > 2
            )

            if len(overlap) >= 2 or phrase_match:
                matches.append(
                    {
                        "id": seed["id"],
                        "content": f"SEED: {seed['what_went_wrong']}",
                        "correct_approach": seed["correct_approach"],
                        "severity": seed.get("severity", "medium"),
                        "domain": seed.get("domain", "general"),
                    }
                )

        return matches

    def _keyword_search(self, query: str, memory_type: str = None) -> list:
        """
        Decompose query into keywords and OR-search the DB.
        Much more effective than exact substring matching.
        """
        if not self.db_path:
            return self._search_mcp(query, memory_type)

        # Extract meaningful keywords (skip short/common words)
        stop_words = {
            "a",
            "an",
            "the",
            "to",
            "in",
            "on",
            "at",
            "is",
            "it",
            "of",
            "and",
            "or",
            "all",
            "for",
        }
        keywords = [w for w in query.lower().split() if len(w) > 2 and w not in stop_words]

        if not keywords:
            return self._search_sqlite(query, memory_type)

        try:
            import sqlite3

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # Build OR query for keyword matching
            like_clauses = " OR ".join(["content LIKE ?" for _ in keywords])
            sql = f"SELECT *, ({' + '.join(['(content LIKE ?)' for _ in keywords])}) as match_score FROM memories WHERE ({like_clauses})"
            params = [f"%{kw}%" for kw in keywords] * 2  # Once for score, once for WHERE

            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)

            if self.project and self.project != "general":
                sql += " AND (project = ? OR project IS NULL OR project = 'general')"
                params.append(self.project)

            sql += " ORDER BY match_score DESC, importance DESC LIMIT 10"

            cursor = conn.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception as e:
            print(f"Keyword search failed: {e}", file=sys.stderr)
            return self._search_sqlite(query, memory_type)

    def _memory_search(self, query: str, memory_type: str = None) -> list:
        """Search the claude-memory MCP server."""
        if self.db_path:
            return self._search_sqlite(query, memory_type)
        return self._search_mcp(query, memory_type)

    def _search_sqlite(self, query: str, memory_type: str = None) -> list:
        """Direct SQLite search when DB path is known."""
        try:
            import sqlite3

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            sql = "SELECT * FROM memories WHERE content LIKE ?"
            params = [f"%{query}%"]

            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)

            if self.project and self.project != "general":
                sql += " AND (project = ? OR project IS NULL OR project = 'general')"
                params.append(self.project)

            sql += " ORDER BY importance DESC, created_at DESC LIMIT 10"

            cursor = conn.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception as e:
            print(f"SQLite search failed: {e}", file=sys.stderr)
            return []

    def _search_mcp(self, query: str, memory_type: str = None) -> list:
        """Search via MCP command (for agents using MCP transport)."""
        # This is a stub — actual MCP call depends on transport
        return []

    def _store_memory(self, content: str, tags: list = None, importance: int = 5):
        """Store a memory entry."""
        if self.db_path:
            self._store_sqlite(content, tags, importance)
        else:
            self._store_mcp(content, tags, importance)

    def _store_sqlite(self, content: str, tags: list = None, importance: int = 5):
        """Store directly to SQLite."""
        try:
            import sqlite3

            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT INTO memories (content, tags, importance, project, memory_type, created_at)
                   VALUES (?, ?, ?, ?, 'correction', datetime('now'))""",
                (content, json.dumps(tags or []), importance, self.project),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"SQLite store failed: {e}", file=sys.stderr)

    def _store_mcp(self, content: str, tags: list = None, importance: int = 5):
        """Store via MCP (stub)."""
        pass

    def _store_correction(self, correction: dict) -> bool:
        """Store a structured correction."""
        content = (
            f"CORRECTION: {correction['what_claude_said']}\n"
            f"Wrong: {correction['what_was_wrong']}\n"
            f"Right: {correction['correct_approach']}\n"
            f"Category: {correction.get('category', 'general')}"
        )
        self._store_memory(
            content, tags=["correction", correction.get("category", "general")], importance=8
        )
        return True

    @staticmethod
    def _severity_to_importance(severity: str) -> int:
        return {"critical": 10, "high": 8, "medium": 6, "low": 4}.get(severity, 5)


# ─── STANDALONE SEEDING ─────────────────────────────────────────


def main():
    """CLI entry point for seeding and synthesis."""
    import argparse

    parser = argparse.ArgumentParser(description="Common Sense Engine")
    parser.add_argument(
        "command",
        choices=["seed", "synthesize", "check"],
        help="seed: load universal corrections, synthesize: find patterns, check: test an action",
    )
    parser.add_argument("--project", default="general", help="Project context")
    parser.add_argument("--action", help="Action to check (for 'check' command)")
    parser.add_argument("--db", help="Path to memory SQLite database")
    parser.add_argument("--seeds", help="Path to seeds JSON file")

    args = parser.parse_args()
    cs = CommonSense(project=args.project, db_path=args.db)

    if args.command == "seed":
        count = cs.seed(args.seeds)
        print(f"Done. {count} corrections loaded.")

    elif args.command == "synthesize":
        patterns = cs.synthesize()
        if patterns:
            for p in patterns:
                print(f"\n[{p['domain'].upper()}] {p['count']} corrections")
                print(f"  Insight: {p['insight']}")
                for item in p["items"]:
                    print(f"    - {item[:100]}...")
        else:
            print("No patterns found yet. Need more corrections.")

    elif args.command == "check":
        if not args.action:
            print("--action required for check command")
            sys.exit(1)
        result = cs.before(args.action)
        if result.blocked:
            print(f"BLOCKED: {result.reason}")
        elif result.warnings:
            print(f"WARNINGS ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  - {w}")
        else:
            print(f"OK (confidence: {result.confidence:.0%})")


if __name__ == "__main__":
    main()

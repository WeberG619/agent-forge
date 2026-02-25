#!/usr/bin/env python3
"""
Workflow Learning Engine
Tracks user actions, learns patterns, and predicts/suggests next steps.

This transforms Claude from reactive to truly proactive by:
1. Recording action sequences (what user does after what)
2. Learning common workflows per project type
3. Predicting next likely actions
4. Suggesting optimizations and shortcuts
5. Detecting anomalies (user doing something unusual)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass

# Paths
BASE_DIR = Path(__file__).parent
WORKFLOWS_DB = BASE_DIR / "workflows.db"
PATTERNS_FILE = BASE_DIR / "learned_patterns.json"


@dataclass
class Action:
    """Represents a user action."""

    timestamp: str
    action_type: str  # app_switch, file_open, view_change, command, etc.
    details: Dict
    project: Optional[str] = None
    context: Optional[str] = None  # What was happening when this occurred


@dataclass
class WorkflowPattern:
    """A learned workflow pattern."""

    name: str
    trigger: str
    sequence: List[str]
    frequency: int
    avg_duration_seconds: float
    project_types: List[str]
    success_rate: float


class WorkflowDatabase:
    """SQLite database for workflow storage."""

    def __init__(self):
        self.db_path = WORKFLOWS_DB
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Actions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                details TEXT,
                project TEXT,
                context TEXT,
                session_id TEXT
            )
        """)

        # Sequences table (learned patterns)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sequences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_action TEXT NOT NULL,
                next_action TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                avg_gap_seconds REAL,
                project TEXT,
                last_seen TEXT
            )
        """)

        # Workflows table (named multi-step patterns)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                steps TEXT,
                frequency INTEGER DEFAULT 1,
                avg_duration_seconds REAL,
                project_types TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0
            )
        """)

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at TEXT,
                ended_at TEXT,
                project TEXT,
                actions_count INTEGER DEFAULT 0,
                summary TEXT
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_type ON actions(action_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_project ON actions(project)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sequences_trigger ON sequences(trigger_action)"
        )

        conn.commit()
        conn.close()

    def record_action(self, action: Action, session_id: str = None):
        """Record a user action."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO actions (timestamp, action_type, details, project, context, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                action.timestamp,
                action.action_type,
                json.dumps(action.details),
                action.project,
                action.context,
                session_id,
            ),
        )

        conn.commit()
        conn.close()

    def learn_sequence(
        self, trigger: str, next_action: str, gap_seconds: float, project: str = None
    ):
        """Learn or update a sequence pattern."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if exists
        cursor.execute(
            """
            SELECT id, count, avg_gap_seconds FROM sequences
            WHERE trigger_action = ? AND next_action = ? AND (project = ? OR project IS NULL)
        """,
            (trigger, next_action, project),
        )

        row = cursor.fetchone()
        if row:
            # Update existing
            new_count = row[1] + 1
            new_avg = ((row[2] * row[1]) + gap_seconds) / new_count
            cursor.execute(
                """
                UPDATE sequences
                SET count = ?, avg_gap_seconds = ?, last_seen = ?
                WHERE id = ?
            """,
                (new_count, new_avg, datetime.now().isoformat(), row[0]),
            )
        else:
            # Insert new
            cursor.execute(
                """
                INSERT INTO sequences (trigger_action, next_action, count, avg_gap_seconds, project, last_seen)
                VALUES (?, ?, 1, ?, ?, ?)
            """,
                (trigger, next_action, gap_seconds, project, datetime.now().isoformat()),
            )

        conn.commit()
        conn.close()

    def get_likely_next_actions(
        self, current_action: str, project: str = None, limit: int = 5
    ) -> List[Tuple[str, float]]:
        """Get most likely next actions based on history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get sequences sorted by frequency
        cursor.execute(
            """
            SELECT next_action, count, avg_gap_seconds
            FROM sequences
            WHERE trigger_action = ?
            AND (project = ? OR project IS NULL)
            ORDER BY count DESC
            LIMIT ?
        """,
            (current_action, project, limit),
        )

        results = []
        total = sum(row[1] for row in cursor.fetchall())

        cursor.execute(
            """
            SELECT next_action, count, avg_gap_seconds
            FROM sequences
            WHERE trigger_action = ?
            AND (project = ? OR project IS NULL)
            ORDER BY count DESC
            LIMIT ?
        """,
            (current_action, project, limit),
        )

        for row in cursor.fetchall():
            probability = row[1] / total if total > 0 else 0
            results.append((row[0], probability, row[2]))

        conn.close()
        return results

    def get_recent_actions(self, limit: int = 20) -> List[Dict]:
        """Get recent actions."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM actions
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results


class WorkflowLearner:
    """Learns workflow patterns from action history."""

    def __init__(self):
        self.db = WorkflowDatabase()
        self.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.last_action: Optional[Action] = None
        self.last_action_time: Optional[datetime] = None

    def record(self, action_type: str, details: Dict, project: str = None, context: str = None):
        """Record an action and learn from it."""
        now = datetime.now()

        action = Action(
            timestamp=now.isoformat(),
            action_type=action_type,
            details=details,
            project=project,
            context=context,
        )

        # Record to database
        self.db.record_action(action, self.current_session_id)

        # Learn sequence if we have a previous action
        if self.last_action and self.last_action_time:
            gap = (now - self.last_action_time).total_seconds()

            # Only learn if gap is reasonable (< 5 minutes)
            if gap < 300:
                trigger = (
                    f"{self.last_action.action_type}:{self.last_action.details.get('name', '')}"
                )
                next_act = f"{action_type}:{details.get('name', '')}"
                self.db.learn_sequence(trigger, next_act, gap, project)

        self.last_action = action
        self.last_action_time = now

    def predict_next(self, current_action: str = None, project: str = None) -> List[Dict]:
        """Predict likely next actions."""
        if current_action is None and self.last_action:
            current_action = (
                f"{self.last_action.action_type}:{self.last_action.details.get('name', '')}"
            )

        if not current_action:
            return []

        predictions = self.db.get_likely_next_actions(current_action, project)

        return [
            {
                "action": pred[0],
                "probability": f"{pred[1]:.0%}",
                "typical_delay": f"{pred[2]:.1f}s" if len(pred) > 2 else "unknown",
            }
            for pred in predictions
        ]

    def detect_anomaly(self, action_type: str, details: Dict, project: str = None) -> Optional[str]:
        """Detect if current action is unusual."""
        if not self.last_action:
            return None

        trigger = f"{self.last_action.action_type}:{self.last_action.details.get('name', '')}"
        current = f"{action_type}:{details.get('name', '')}"

        predictions = self.db.get_likely_next_actions(trigger, project, limit=10)

        # Check if current action is in predictions
        expected_actions = [p[0] for p in predictions]

        if predictions and current not in expected_actions:
            return f"Unusual: After '{trigger}', you usually do one of: {expected_actions[:3]}. You're doing '{current}' instead."

        return None


class ActionRecorder:
    """Records actions from various sources."""

    def __init__(self):
        self.learner = WorkflowLearner()
        self.action_parsers = {
            "app_switch": self._parse_app_switch,
            "file_open": self._parse_file_open,
            "command": self._parse_command,
            "clipboard": self._parse_clipboard,
        }

    def _parse_app_switch(self, data: Dict) -> Tuple[str, Dict]:
        """Parse application switch."""
        app = data.get("app", "unknown")
        return "app_switch", {"name": app, "from": data.get("from"), "to": data.get("to")}

    def _parse_file_open(self, data: Dict) -> Tuple[str, Dict]:
        """Parse file open action."""
        path = data.get("path", "")
        ext = Path(path).suffix.lower()
        return f"file_open_{ext}", {"name": Path(path).name, "path": path}

    def _parse_command(self, data: Dict) -> Tuple[str, Dict]:
        """Parse a generic command action."""
        name = data.get("name", "unknown")
        return "command", {"name": name, "params": data.get("params", {})}

    def _parse_clipboard(self, data: Dict) -> Tuple[str, Dict]:
        """Parse clipboard action."""
        content_type = data.get("type", "text")
        return f"clipboard_{content_type}", {"name": content_type, "length": data.get("length", 0)}

    def record(self, source: str, data: Dict, project: str = None):
        """Record action from a source."""
        if source in self.action_parsers:
            action_type, details = self.action_parsers[source](data)
        else:
            action_type = source
            details = data

        # Check for anomaly
        anomaly = self.learner.detect_anomaly(action_type, details, project)

        # Record
        self.learner.record(action_type, details, project)

        return {
            "recorded": True,
            "action_type": action_type,
            "anomaly": anomaly,
            "predictions": self.learner.predict_next(project=project),
        }


class PatternAnalyzer:
    """Analyzes learned sequences to discover multi-step workflow patterns."""

    PATTERNS_FILE = BASE_DIR / "learned_patterns.json"
    MIN_FREQUENCY = 3

    def __init__(self):
        self.db = WorkflowDatabase()

    def get_frequent_sequences(self, min_count=3, min_gap=0.5):
        """Get all sequences that occur at least min_count times.
        Filters out polling artifacts (transitions with near-zero gaps)."""
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT trigger_action, next_action, count, avg_gap_seconds, project, last_seen
            FROM sequences
            WHERE count >= ?
            AND (avg_gap_seconds IS NULL OR avg_gap_seconds >= ?)
            AND trigger_action != next_action
            ORDER BY count DESC
        """,
            (min_count, min_gap),
        )
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def discover_chains(self, min_count=3, max_chain_length=8):
        """Discover multi-step workflow chains from bigram sequences.
        Focuses on focus/open events and filters out daemon polling noise."""
        sequences = self.get_frequent_sequences(min_count, min_gap=0.5)
        if not sequences:
            # Try with lower gap threshold
            sequences = self.get_frequent_sequences(min_count, min_gap=0.1)
        if not sequences:
            return []

        # Prioritize focus events (real user actions) over close events (often batch artifacts)
        focus_sequences = [
            s
            for s in sequences
            if "focus:" in s["trigger_action"] or "open:" in s["trigger_action"]
        ]
        if len(focus_sequences) >= 5:
            sequences = focus_sequences

        # Build adjacency map: trigger -> [(next, count, gap)]
        adjacency = defaultdict(list)
        for seq in sequences:
            adjacency[seq["trigger_action"]].append(
                {
                    "next": seq["next_action"],
                    "count": seq["count"],
                    "gap": seq["avg_gap_seconds"] or 0,
                    "project": seq["project"],
                }
            )

        # Find all triggers and next actions
        all_triggers = set(s["trigger_action"] for s in sequences)

        # Prefer starting points that begin chains (triggers not often reached from elsewhere)
        start_candidates = sorted(
            all_triggers, key=lambda t: sum(1 for s in sequences if s["next_action"] == t)
        )

        chains = []
        seen_chain_keys = set()

        for start in start_candidates:
            # DFS to find chains
            stack = [(start, [start], 0, float("inf"))]

            while stack:
                current, path, total_gap, min_freq = stack.pop()

                if len(path) >= max_chain_length:
                    chain_key = "|".join(path)
                    if chain_key not in seen_chain_keys and len(path) >= 3:
                        seen_chain_keys.add(chain_key)
                        chains.append(
                            {
                                "steps": list(path),
                                "length": len(path),
                                "min_frequency": min_freq,
                                "total_gap_seconds": total_gap,
                            }
                        )
                    continue

                next_actions = adjacency.get(current, [])
                extended = False

                for na in sorted(next_actions, key=lambda x: x["count"], reverse=True)[:3]:
                    next_node = na["next"]
                    if next_node not in path:
                        new_min = min(min_freq, na["count"])
                        stack.append(
                            (next_node, path + [next_node], total_gap + na["gap"], new_min)
                        )
                        extended = True

                if not extended and len(path) >= 3:
                    chain_key = "|".join(path)
                    if chain_key not in seen_chain_keys:
                        seen_chain_keys.add(chain_key)
                        chains.append(
                            {
                                "steps": list(path),
                                "length": len(path),
                                "min_frequency": min_freq,
                                "total_gap_seconds": total_gap,
                            }
                        )

        # Score by length * frequency, deduplicate subsets
        chains.sort(key=lambda c: c["length"] * c["min_frequency"], reverse=True)

        final_chains = []
        for chain in chains:
            steps_str = "|".join(chain["steps"])
            is_subset = any(steps_str in "|".join(e["steps"]) for e in final_chains)
            if not is_subset:
                final_chains.append(chain)

        return final_chains[:20]

    def analyze_and_export(self, min_count=3):
        """Run full analysis and export to learned_patterns.json."""
        chains = self.discover_chains(min_count)
        frequent_pairs = self.get_frequent_sequences(min_count)

        # Get total action count for context
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM actions")
        total_actions = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sequences")
        total_sequences = cursor.fetchone()[0]
        conn.close()

        output = {
            "analyzed_at": datetime.now().isoformat(),
            "total_actions_recorded": total_actions,
            "total_unique_sequences": total_sequences,
            "frequent_sequence_count": len(frequent_pairs),
            "workflow_candidates": [],
            "frequent_transitions": [],
        }

        # Format chains as workflow candidates
        for i, chain in enumerate(chains):
            steps_readable = []
            for s in chain["steps"]:
                parts = s.split(":", 1)
                steps_readable.append(parts[1] if len(parts) > 1 else s)

            name = " -> ".join(steps_readable[:5])
            if len(steps_readable) > 5:
                name += f" ... ({len(steps_readable)} steps)"

            output["workflow_candidates"].append(
                {
                    "id": f"wf_candidate_{i + 1}",
                    "name": name,
                    "steps": chain["steps"],
                    "steps_readable": steps_readable,
                    "step_count": chain["length"],
                    "frequency": chain["min_frequency"],
                    "avg_duration_seconds": round(chain["total_gap_seconds"], 1),
                    "status": "candidate",
                    "discovered_at": datetime.now().isoformat(),
                }
            )

        # Add frequent pairs
        for pair in frequent_pairs[:30]:
            t_parts = pair["trigger_action"].split(":", 1)
            n_parts = pair["next_action"].split(":", 1)
            output["frequent_transitions"].append(
                {
                    "from": pair["trigger_action"],
                    "to": pair["next_action"],
                    "from_readable": t_parts[1] if len(t_parts) > 1 else t_parts[0],
                    "to_readable": n_parts[1] if len(n_parts) > 1 else n_parts[0],
                    "count": pair["count"],
                    "avg_gap_seconds": round(pair["avg_gap_seconds"] or 0, 1),
                }
            )

        # Atomic write
        temp_file = self.PATTERNS_FILE.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(output, f, indent=2)
        temp_file.replace(self.PATTERNS_FILE)

        return output


class AutoFixer:
    """Suggests and executes fixes for detected issues."""

    def __init__(self):
        self.fixes = {
            "project_mismatch": self._fix_project_mismatch,
            "missing_file": self._fix_missing_file,
        }

    def _fix_project_mismatch(self, context: Dict) -> Dict:
        """Generate fix for project mismatch."""
        app_a_project = context.get("app_a_project")
        app_b_project = context.get("app_b_project")

        return {
            "issue": f"App A has '{app_a_project}' but App B has '{app_b_project}'",
            "options": [
                {
                    "label": f"Open {app_b_project} in App A",
                    "action": "open_project",
                    "params": {"project": app_b_project, "target": "app_a"},
                },
                {
                    "label": f"Open {app_a_project} in App B",
                    "action": "open_project",
                    "params": {"project": app_a_project, "target": "app_b"},
                },
                {"label": "Keep working (ignore mismatch)", "action": "ignore"},
            ],
        }

    def _fix_missing_file(self, context: Dict) -> Dict:
        """Generate fix for a missing file reference."""
        missing = context.get("missing_file", "unknown")

        return {
            "issue": f"Referenced file not found: {missing}",
            "options": [
                {
                    "label": "Search for similar files",
                    "action": "search_files",
                    "params": {"query": missing},
                },
                {"label": "Ignore", "action": "ignore"},
            ],
        }

    def suggest_fix(self, issue_type: str, context: Dict) -> Optional[Dict]:
        """Get fix suggestion for an issue."""
        if issue_type in self.fixes:
            return self.fixes[issue_type](context)
        return None

    def execute_fix(self, action: str, params: Dict) -> Dict:
        """Execute a fix action."""
        return {
            "action": action,
            "params": params,
            "status": "ready_to_execute",
            "command": self._generate_command(action, params),
        }

    def _generate_command(self, action: str, params: Dict) -> str:
        """Generate the actual command to execute."""
        if action == "open_project":
            return (
                f"open_project(project='{params.get('project')}', target='{params.get('target')}')"
            )
        elif action == "search_files":
            return f"search_files(query='{params.get('query')}')"
        return f"# Action: {action}"


def _extract_project_from_title(title: str) -> Optional[str]:
    """Extract project name from a window title.
    Uses bracket patterns common in many applications (e.g., 'App - [ProjectName - View]')."""
    if not title:
        return None
    # Try to extract from bracket pattern: "App - [ProjectName - View]"
    if "[" in title and "]" in title:
        bracket_content = title.split("[")[1].split("]")[0]
        if " - " in bracket_content:
            return bracket_content.split(" - ")[0].strip()
        return bracket_content.strip()
    return None


def main():
    """CLI interface."""
    import sys

    recorder = ActionRecorder()
    fixer = AutoFixer()

    if len(sys.argv) < 2:
        print(
            json.dumps(
                {
                    "commands": [
                        "record <source> <json_data>",
                        "predict [action]",
                        "history [limit]",
                        "fix <issue_type> <context_json>",
                        "analyze [min_count]",
                        "backfill",
                    ]
                },
                indent=2,
            )
        )
        return

    cmd = sys.argv[1]

    if cmd == "record" and len(sys.argv) >= 4:
        source = sys.argv[2]
        data = json.loads(sys.argv[3])
        project = sys.argv[4] if len(sys.argv) > 4 else None
        result = recorder.record(source, data, project)
        print(json.dumps(result, indent=2))

    elif cmd == "predict":
        action = sys.argv[2] if len(sys.argv) > 2 else None
        predictions = recorder.learner.predict_next(action)
        print(json.dumps({"predictions": predictions}, indent=2))

    elif cmd == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        actions = recorder.learner.db.get_recent_actions(limit)
        print(json.dumps({"actions": actions}, indent=2))

    elif cmd == "fix" and len(sys.argv) >= 4:
        issue_type = sys.argv[2]
        context = json.loads(sys.argv[3])
        suggestion = fixer.suggest_fix(issue_type, context)
        print(json.dumps(suggestion, indent=2))

    elif cmd == "analyze":
        min_count = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        analyzer = PatternAnalyzer()
        result = analyzer.analyze_and_export(min_count)
        print(
            json.dumps(
                {
                    "candidates": len(result.get("workflow_candidates", [])),
                    "transitions": len(result.get("frequent_transitions", [])),
                    "total_actions": result.get("total_actions_recorded", 0),
                    "exported_to": str(PatternAnalyzer.PATTERNS_FILE),
                },
                indent=2,
            )
        )

    elif cmd == "backfill":
        # Backfill from events.ndjson into workflows.db using batched SQL
        events_file = BASE_DIR / "events.ndjson"
        if not events_file.exists():
            print('{"error": "events.ndjson not found"}')
            return

        # Parse all events first
        parsed_events = []
        errors = 0
        with open(events_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("event_type", event.get("type", ""))
                    details_str = event.get("details", "")
                    ts = event.get("ts", event.get("timestamp", ""))

                    app_name = ""
                    window_title = ""
                    if ": " in details_str:
                        app_name, window_title = details_str.split(": ", 1)
                    else:
                        app_name = details_str

                    project = _extract_project_from_title(window_title)

                    if event_type in ("app_opened", "focus_changed"):
                        action_type = f"focus:{app_name}"
                    elif event_type == "app_closed":
                        action_type = f"close:{app_name}"
                    else:
                        continue

                    parsed_events.append(
                        {
                            "ts": ts,
                            "action_type": action_type,
                            "details": json.dumps({"name": app_name, "title": window_title}),
                            "project": project,
                        }
                    )
                except Exception:
                    errors += 1

        # Batch insert into database
        conn = sqlite3.connect(WORKFLOWS_DB)
        cursor = conn.cursor()

        # Insert all actions in one transaction
        cursor.executemany(
            """
            INSERT INTO actions (timestamp, action_type, details, project, context, session_id)
            VALUES (:ts, :action_type, :details, :project, NULL, 'backfill')
        """,
            parsed_events,
        )

        # Learn sequences from consecutive events
        seq_count = 0
        for i in range(1, len(parsed_events)):
            prev = parsed_events[i - 1]
            curr = parsed_events[i]

            # Calculate gap
            try:
                t1 = datetime.fromisoformat(prev["ts"])
                t2 = datetime.fromisoformat(curr["ts"])
                gap = (t2 - t1).total_seconds()
            except (ValueError, TypeError):
                gap = 999

            if gap > 300:  # Skip if > 5 min gap
                continue

            trigger = prev["action_type"]
            next_act = curr["action_type"]
            project = curr["project"]

            # Upsert sequence
            cursor.execute(
                """
                SELECT id, count, avg_gap_seconds FROM sequences
                WHERE trigger_action = ? AND next_action = ?
            """,
                (trigger, next_act),
            )
            row = cursor.fetchone()

            if row:
                new_count = row[1] + 1
                new_avg = ((row[2] * row[1]) + gap) / new_count
                cursor.execute(
                    """
                    UPDATE sequences SET count = ?, avg_gap_seconds = ?, last_seen = ?
                    WHERE id = ?
                """,
                    (new_count, new_avg, curr["ts"], row[0]),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO sequences (trigger_action, next_action, count, avg_gap_seconds, project, last_seen)
                    VALUES (?, ?, 1, ?, ?, ?)
                """,
                    (trigger, next_act, gap, project, curr["ts"]),
                )
            seq_count += 1

        conn.commit()
        conn.close()

        # Run analysis after backfill
        analyzer = PatternAnalyzer()
        result = analyzer.analyze_and_export(min_count=3)

        print(
            json.dumps(
                {
                    "backfilled": len(parsed_events),
                    "sequences_learned": seq_count,
                    "errors": errors,
                    "candidates_found": len(result.get("workflow_candidates", [])),
                    "transitions_found": len(result.get("frequent_transitions", [])),
                },
                indent=2,
            )
        )

    else:
        print(f'{{"error": "Unknown command: {cmd}"}}')


if __name__ == "__main__":
    main()

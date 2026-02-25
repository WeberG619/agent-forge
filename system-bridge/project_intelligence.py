#!/usr/bin/env python3
"""
Project Intelligence Engine
Provides proactive intelligence by:
1. Correlating open files/apps to known projects
2. Detecting project context switches
3. Predicting user intent based on patterns
4. Alerting to mismatches and anomalies

This is Claude's "brain" for understanding what you're working on.
"""

import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

# Paths - relative to this module
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "live_state.json"
INTELLIGENCE_FILE = BASE_DIR / "intelligence.json"
PATTERNS_FILE = BASE_DIR / "learned_patterns.json"


@dataclass
class ProjectContext:
    """Represents the current project context."""
    project_name: str
    confidence: float  # 0-1
    sources: List[str]  # What indicated this project
    related_files: List[str]
    last_memories: List[Dict]
    unfinished_tasks: List[str]
    corrections: List[str]
    suggested_actions: List[str]
    mismatches: List[str]


@dataclass
class WorkflowPattern:
    """A learned pattern of user behavior."""
    trigger: str  # What triggers this pattern
    typical_sequence: List[str]  # What usually follows
    frequency: int  # How often seen
    last_seen: str


class ProjectCorrelator:
    """Correlates files and applications to projects.

    Project patterns can be configured by providing a patterns dictionary
    or by loading from a JSON configuration file.
    """

    def __init__(self, patterns: Optional[Dict] = None, patterns_file: Optional[Path] = None):
        """Initialize with optional patterns dict or patterns file path.

        Args:
            patterns: Dictionary of project patterns. Each key is a project_id,
                      and the value has 'patterns' (list of regex), 'aliases' (list of strings),
                      and optionally 'path', 'typical_files', etc.
            patterns_file: Path to a JSON file with project patterns.
        """
        if patterns:
            self.project_patterns = patterns
        elif patterns_file and patterns_file.exists():
            with open(patterns_file) as f:
                self.project_patterns = json.load(f)
        else:
            self.project_patterns = self._load_default_patterns()

    def _load_default_patterns(self) -> Dict:
        """Load default project patterns. Override or extend for your projects."""
        # Check for a project_patterns.json file next to this module
        config_file = BASE_DIR / "project_patterns.json"
        if config_file.exists():
            with open(config_file) as f:
                return json.load(f)

        # Return empty patterns - users should configure their own
        return {}

    def identify_project(self, text: str) -> Tuple[Optional[str], float]:
        """Identify project from text (filename, window title, etc.)."""
        text_lower = text.lower()

        for project_id, config in self.project_patterns.items():
            for pattern in config.get("patterns", []):
                if re.search(pattern, text_lower):
                    return project_id, 0.9

            for alias in config.get("aliases", []):
                if alias.lower() in text_lower:
                    return project_id, 0.8

        return None, 0.0

    def correlate_from_state(self, state: Dict) -> Dict[str, List[Tuple[str, float]]]:
        """Analyze system state and identify projects from all sources."""
        findings = defaultdict(list)

        # Check all open applications
        for app in state.get("applications", []):
            title = app.get("MainWindowTitle", "")
            process = app.get("ProcessName", "")

            # Skip system apps
            if process.lower() in ["explorer", "applicationframehost", "systemsettings"]:
                continue

            project, conf = self.identify_project(title)
            if project:
                findings[project].append((f"{process}:{title[:50]}", conf))

        # Check any app-specific state sections
        for key, app_state in state.items():
            if isinstance(app_state, dict) and app_state.get("document"):
                doc = app_state["document"]
                project, conf = self.identify_project(doc)
                if project:
                    findings[project].append((key, conf))

        return dict(findings)


class MemoryLoader:
    """Loads relevant memories for a project context.

    Requires a path to a memory database (SQLite) with a 'memories' table.
    If no database is available, returns empty context gracefully.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def get_project_context(self, project_name: str) -> Dict:
        """Get all relevant context for a project."""
        if not self.db_path or not self.db_path.exists():
            return {}

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        context = {
            "recent_memories": [],
            "corrections": [],
            "unfinished_tasks": [],
            "decisions": [],
        }

        # Recent memories
        cursor.execute("""
            SELECT content, memory_type, importance, created_at
            FROM memories
            WHERE project = ? OR content LIKE ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (project_name, f"%{project_name}%"))

        for row in cursor.fetchall():
            context["recent_memories"].append({
                "content": row["content"][:300],
                "type": row["memory_type"],
                "importance": row["importance"],
                "created": row["created_at"]
            })

        # Corrections
        cursor.execute("""
            SELECT content FROM memories
            WHERE memory_type = 'error'
            AND tags LIKE '%correction%'
            AND (project = ? OR content LIKE ?)
            ORDER BY created_at DESC
            LIMIT 5
        """, (project_name, f"%{project_name}%"))

        for row in cursor.fetchall():
            content = row["content"]
            if "### Correct Approach:" in content:
                approach = content.split("### Correct Approach:")[1]
                approach = approach.split("**Category**")[0].strip()
                context["corrections"].append(approach[:200])

        # Unfinished tasks (from session summaries)
        cursor.execute("""
            SELECT content FROM memories
            WHERE tags LIKE '%session-summary%'
            AND content LIKE '%### Next Steps%'
            AND (project = ? OR content LIKE ?)
            ORDER BY created_at DESC
            LIMIT 3
        """, (project_name, f"%{project_name}%"))

        for row in cursor.fetchall():
            content = row["content"]
            if "### Next Steps" in content:
                steps_section = content.split("### Next Steps")[1]
                steps = [s.strip() for s in steps_section.split('\n')
                        if s.strip().startswith('-')]
                context["unfinished_tasks"].extend(steps[:3])

        # Recent decisions
        cursor.execute("""
            SELECT content FROM memories
            WHERE memory_type = 'decision'
            AND (project = ? OR content LIKE ?)
            ORDER BY created_at DESC
            LIMIT 5
        """, (project_name, f"%{project_name}%"))

        for row in cursor.fetchall():
            context["decisions"].append(row["content"][:150])

        conn.close()
        return context


class IntentPredictor:
    """Predicts user intent based on current state and learned patterns."""

    def __init__(self):
        self.patterns = self._load_patterns()

    def _load_patterns(self) -> Dict:
        """Load learned workflow patterns."""
        if PATTERNS_FILE.exists():
            with open(PATTERNS_FILE) as f:
                return json.load(f)
        return {"workflows": [], "sequences": {}}

    def _save_patterns(self):
        """Save learned patterns."""
        with open(PATTERNS_FILE, 'w') as f:
            json.dump(self.patterns, f, indent=2)

    def learn_sequence(self, actions: List[str]):
        """Learn from a sequence of actions."""
        if len(actions) < 2:
            return

        for i in range(len(actions) - 1):
            trigger = actions[i]
            followup = actions[i + 1]

            if trigger not in self.patterns["sequences"]:
                self.patterns["sequences"][trigger] = {}

            if followup not in self.patterns["sequences"][trigger]:
                self.patterns["sequences"][trigger][followup] = 0

            self.patterns["sequences"][trigger][followup] += 1

        self._save_patterns()

    def predict_next_actions(self, current_state: Dict, project: str) -> List[str]:
        """Predict likely next actions based on current state.

        This is a generic prediction engine. Extend this method with
        application-specific predictions for your workflow.
        """
        predictions = []

        # Check active window for context clues
        active_window = current_state.get("active_window", "")
        if active_window:
            # Common patterns based on active window content
            active_lower = active_window.lower()
            if "code" in active_lower or "editor" in active_lower:
                predictions.append("User may want to: Run tests, commit changes, or switch to browser")
            elif "browser" in active_lower or "chrome" in active_lower:
                predictions.append("User may want to: Research, review docs, or switch back to editor")
            elif "terminal" in active_lower or "console" in active_lower:
                predictions.append("User may want to: Run commands, check logs, or return to editor")

        return predictions

    def detect_mismatches(self, correlations: Dict) -> List[str]:
        """Detect when user might be working on wrong project."""
        mismatches = []

        if len(correlations) > 1:
            projects = list(correlations.keys())
            # Alert if multiple distinct projects are detected simultaneously
            if len(projects) >= 2:
                project_list = ', '.join(projects[:3])
                mismatches.append(
                    f"Multiple projects detected simultaneously: {project_list}. "
                    f"Make sure you're working on the intended project."
                )

        return mismatches


class ActionSuggester:
    """Suggests actions based on context."""

    def suggest_actions(self, context: ProjectContext) -> List[str]:
        """Generate suggested actions for current context."""
        suggestions = []

        # If there are unfinished tasks, suggest continuing them
        if context.unfinished_tasks:
            suggestions.append(f"CONTINUE: {context.unfinished_tasks[0]}")

        # If there are corrections, remind about them
        if context.corrections:
            suggestions.append(f"REMEMBER: {context.corrections[0][:100]}...")

        # If there are mismatches, prioritize fixing them
        if context.mismatches:
            suggestions.insert(0, f"FIX: {context.mismatches[0]}")

        return suggestions


class ProjectIntelligence:
    """Main intelligence engine that ties everything together."""

    def __init__(self, memory_db_path: Optional[Path] = None,
                 project_patterns: Optional[Dict] = None):
        """Initialize the project intelligence engine.

        Args:
            memory_db_path: Optional path to a memory SQLite database.
            project_patterns: Optional dict of project patterns for correlation.
        """
        self.correlator = ProjectCorrelator(patterns=project_patterns)
        self.memory_loader = MemoryLoader(db_path=memory_db_path)
        self.predictor = IntentPredictor()
        self.suggester = ActionSuggester()

    def analyze(self, state: Dict = None) -> ProjectContext:
        """Analyze current state and return full project context."""
        # Load state if not provided
        if state is None:
            if STATE_FILE.exists():
                with open(STATE_FILE) as f:
                    state = json.load(f)
            else:
                state = {}

        # Correlate to projects
        correlations = self.correlator.correlate_from_state(state)

        # Determine primary project
        if correlations:
            # Pick project with most sources and highest confidence
            primary = max(correlations.items(),
                         key=lambda x: sum(c for _, c in x[1]))
            project_name = primary[0]
            confidence = sum(c for _, c in primary[1]) / len(primary[1])
            sources = [s for s, _ in primary[1]]
        else:
            project_name = "unknown"
            confidence = 0.0
            sources = []

        # Load memory context
        memory_context = self.memory_loader.get_project_context(project_name)

        # Detect mismatches
        mismatches = self.predictor.detect_mismatches(correlations)

        # Predict intent
        predictions = self.predictor.predict_next_actions(state, project_name)

        # Build context object
        context = ProjectContext(
            project_name=project_name,
            confidence=confidence,
            sources=sources,
            related_files=[],
            last_memories=memory_context.get("recent_memories", []),
            unfinished_tasks=memory_context.get("unfinished_tasks", []),
            corrections=memory_context.get("corrections", []),
            suggested_actions=predictions,
            mismatches=mismatches,
        )

        # Generate action suggestions
        context.suggested_actions.extend(self.suggester.suggest_actions(context))

        # Save intelligence output
        self._save_intelligence(context)

        return context

    def _save_intelligence(self, context: ProjectContext):
        """Save intelligence output to file."""
        output = asdict(context)
        output["generated_at"] = datetime.now().isoformat()

        with open(INTELLIGENCE_FILE, 'w') as f:
            json.dump(output, f, indent=2)

    def get_briefing(self) -> str:
        """Generate a human-readable briefing."""
        context = self.analyze()

        lines = []
        lines.append("=" * 60)
        lines.append(" PROJECT INTELLIGENCE BRIEFING")
        lines.append("=" * 60)
        lines.append(f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Primary project
        lines.append(f"## DETECTED PROJECT: {context.project_name.upper()}")
        lines.append(f"   Confidence: {context.confidence:.0%}")
        lines.append(f"   Sources: {', '.join(context.sources)}")
        lines.append("")

        # Mismatches (HIGH PRIORITY)
        if context.mismatches:
            lines.append("## [!] MISMATCHES DETECTED")
            for mismatch in context.mismatches:
                lines.append(f"   {mismatch}")
            lines.append("")

        # Corrections to remember
        if context.corrections:
            lines.append("## CORRECTIONS TO REMEMBER")
            for corr in context.corrections[:3]:
                lines.append(f"   > {corr}")
            lines.append("")

        # Unfinished work
        if context.unfinished_tasks:
            lines.append("## UNFINISHED TASKS")
            for task in context.unfinished_tasks[:5]:
                lines.append(f"   {task}")
            lines.append("")

        # Suggested actions
        if context.suggested_actions:
            lines.append("## SUGGESTED ACTIONS")
            for action in context.suggested_actions[:5]:
                lines.append(f"   - {action}")
            lines.append("")

        # Recent context
        if context.last_memories:
            lines.append("## RECENT CONTEXT")
            for mem in context.last_memories[:3]:
                lines.append(f"   [{mem['type']}] {mem['content'][:100]}...")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)


def main():
    """CLI interface."""
    import sys

    intel = ProjectIntelligence()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "analyze":
            context = intel.analyze()
            print(json.dumps(asdict(context), indent=2))

        elif cmd == "briefing":
            print(intel.get_briefing())

        elif cmd == "project":
            context = intel.analyze()
            print(f"Detected: {context.project_name} ({context.confidence:.0%})")

        elif cmd == "mismatches":
            context = intel.analyze()
            if context.mismatches:
                for m in context.mismatches:
                    print(m)
            else:
                print("No mismatches detected")

        else:
            print(f"Unknown command: {cmd}")
            print("Commands: analyze, briefing, project, mismatches")
    else:
        # Default: print briefing
        print(intel.get_briefing())


if __name__ == "__main__":
    main()

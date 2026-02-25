#!/usr/bin/env python3
"""
validate_agents.py — Validate agent definition files for cadre-ai.

Checks:
  .md  agents: required H2 sections present (Capabilities, Workflow, Rules)
  .yaml agents: required top-level fields present (name, description, system_prompt)

Exit codes:
  0 — all agents valid
  1 — one or more validation failures
"""

import sys
import re
from pathlib import Path
import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGENTS_DIR = Path(__file__).parent.parent / "agents"

# Sections that every .md agent must contain (case-insensitive H2 match).
# agent-builder.md deliberately uses "Process" instead of "Workflow" —
# document that as a known exception rather than silently skipping it.
MD_REQUIRED_SECTIONS = {"Capabilities", "Workflow", "Rules"}

# Known exceptions: agent file stem -> set of sections it is allowed to omit.
# Document *why* each exception exists so reviewers understand the intent.
MD_KNOWN_EXCEPTIONS: dict[str, set[str]] = {
    # agent-builder describes capabilities and workflow via ## Output Format / ## Process
    "agent-builder": {"Capabilities", "Workflow"},
    # learning-agent uses ## When to Activate as its workflow equivalent
    "learning-agent": {"Workflow"},
}

# Required top-level fields for every .yaml agent.
YAML_REQUIRED_FIELDS = {"name", "description", "system_prompt"}

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_md_agent(path: Path) -> list[str]:
    """Return a list of error strings for a .md agent file, or [] if valid."""
    errors: list[str] = []
    stem = path.stem

    text = path.read_text(encoding="utf-8")

    # Extract all H2 headings (## Heading)
    found_sections = {
        m.group(1).strip()
        for m in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE)
    }

    allowed_missing = MD_KNOWN_EXCEPTIONS.get(stem, set())
    required = MD_REQUIRED_SECTIONS - allowed_missing

    for section in sorted(required):
        # Case-insensitive check
        if not any(s.lower() == section.lower() for s in found_sections):
            errors.append(f"  missing required section: '## {section}'")

    if not errors and allowed_missing:
        # Still note the exception so it shows in output
        missing_display = ", ".join(sorted(allowed_missing))
        print(f"  [note] known exception — omits: {missing_display}")

    return errors


def validate_yaml_agent(path: Path) -> list[str]:
    """Return a list of error strings for a .yaml agent file, or [] if valid."""
    errors: list[str] = []

    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"  YAML parse error: {exc}"]

    if not isinstance(data, dict):
        return ["  top-level YAML structure must be a mapping"]

    for field in sorted(YAML_REQUIRED_FIELDS):
        if field not in data:
            errors.append(f"  missing required field: '{field}'")
        elif not str(data[field]).strip():
            errors.append(f"  field '{field}' is present but empty")

    return errors


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print(f"ERROR: agents directory not found: {AGENTS_DIR}", file=sys.stderr)
        return 1

    md_files = sorted(AGENTS_DIR.glob("*.md"))
    yaml_files = sorted(AGENTS_DIR.glob("*.yaml"))

    if not md_files and not yaml_files:
        print(f"WARNING: no agent files found in {AGENTS_DIR}", file=sys.stderr)
        return 1

    total = 0
    failed = 0

    print(f"Validating {len(md_files)} .md agents and {len(yaml_files)} .yaml agents\n")

    # --- .md agents ---
    for path in md_files:
        total += 1
        print(f"[md]  {path.name}")
        errors = validate_md_agent(path)
        if errors:
            failed += 1
            for err in errors:
                print(err)
            print("  FAIL\n")
        else:
            print("  OK\n")

    # --- .yaml agents ---
    for path in yaml_files:
        total += 1
        print(f"[yaml] {path.name}")
        errors = validate_yaml_agent(path)
        if errors:
            failed += 1
            for err in errors:
                print(err)
            print("  FAIL\n")
        else:
            print("  OK\n")

    # --- Summary ---
    print("-" * 50)
    passed = total - failed
    print(f"Results: {passed}/{total} passed")

    if failed:
        print(f"\n{failed} agent(s) failed validation.", file=sys.stderr)
        return 1

    print("\nAll agents valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

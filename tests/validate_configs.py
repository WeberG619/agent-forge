#!/usr/bin/env python3
"""
validate_configs.py — Validate all JSON and YAML/YML config files in cadre-ai.

Walks the repository and attempts to parse every .json, .yaml, and .yml file.
Excludes:
  - .git/
  - node_modules/
  - __pycache__/
  - *.min.js / *.min.css (minified assets that may contain JSON-like fragments)

Exit codes:
  0 — all files parse successfully
  1 — one or more parse failures
"""

import json
import sys
from pathlib import Path
import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", "dist", "build"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iter_files(root: Path, suffixes: set[str]):
    """Yield all files under root with the given suffixes, skipping excluded dirs."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        # Skip any path component that matches an excluded directory
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in suffixes:
            yield path


def validate_json(path: Path) -> str | None:
    """Return error string if file fails JSON parse, else None."""
    try:
        with path.open(encoding="utf-8") as fh:
            json.load(fh)
        return None
    except json.JSONDecodeError as exc:
        return f"JSON parse error at line {exc.lineno} col {exc.colno}: {exc.msg}"
    except UnicodeDecodeError as exc:
        return f"Encoding error: {exc}"


def validate_yaml(path: Path) -> str | None:
    """Return error string if file fails YAML parse, else None."""
    try:
        with path.open(encoding="utf-8") as fh:
            # Use safe_load_all to handle multi-document YAML files
            list(yaml.safe_load_all(fh))
        return None
    except yaml.YAMLError as exc:
        return f"YAML parse error: {exc}"
    except UnicodeDecodeError as exc:
        return f"Encoding error: {exc}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    json_files = list(iter_files(REPO_ROOT, {".json"}))
    yaml_files = list(iter_files(REPO_ROOT, {".yaml", ".yml"}))

    all_files = [("JSON", path, validate_json) for path in json_files] + [
        ("YAML", path, validate_yaml) for path in yaml_files
    ]

    if not all_files:
        print("WARNING: no JSON or YAML files found.", file=sys.stderr)
        return 0

    print(f"Validating {len(json_files)} JSON file(s) and {len(yaml_files)} YAML file(s)\n")

    total = 0
    failed = 0

    for kind, path, validator in all_files:
        total += 1
        rel = path.relative_to(REPO_ROOT)
        error = validator(path)
        if error:
            failed += 1
            print(f"FAIL [{kind}] {rel}")
            print(f"     {error}")
        else:
            print(f"OK   [{kind}] {rel}")

    print()
    print("-" * 60)
    passed = total - failed
    print(f"Results: {passed}/{total} passed")

    if failed:
        print(f"\n{failed} file(s) failed validation.", file=sys.stderr)
        return 1

    print("\nAll config files valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

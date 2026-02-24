"""
cadre_ai.plugins — Plugin manager for the cadre-ai agent framework.

Supports installing, listing, validating, searching, and removing
custom agent plugins.  Uses only stdlib: no external dependencies.

Install locations:
  ~/.claude/agents/          Primary — Claude Code loads agents from here.
  ~/.cadre-ai/plugins/       Secondary — cadre-managed plugin store.

Registry:
  The community registry is a JSON file bundled with this package at
  plugins/registry.json.  A future release will support fetching a
  remote registry snapshot.
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CLAUDE_AGENTS_DIR: Path = Path.home() / ".claude" / "agents"
CADRE_PLUGINS_DIR: Path = Path.home() / ".cadre-ai" / "plugins"

# Registry bundled with the package (two levels up from cadre_ai/plugins.py)
_PACKAGE_ROOT = Path(__file__).parent.parent
BUNDLED_REGISTRY: Path = _PACKAGE_ROOT / "plugins" / "registry.json"

# Required markdown headings for .md agent files
_REQUIRED_MD_SECTIONS = {"## Capabilities", "## Rules"}

# Required top-level keys for .yaml agent files
_REQUIRED_YAML_KEYS = {"name", "description", "system_prompt"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_installed() -> list[dict]:
    """Return all installed agents from ~/.claude/agents/ and ~/.cadre-ai/plugins/.

    Each entry is a dict with keys:
        name        — agent slug (filename without extension)
        format      — "md" or "yaml"
        source      — "claude" | "cadre"
        path        — absolute path as a string

    Returns:
        Sorted list of agent dicts, deduplicated by name (claude wins over cadre).
    """
    seen: dict[str, dict] = {}

    for source_dir, source_label in [
        (CLAUDE_AGENTS_DIR, "claude"),
        (CADRE_PLUGINS_DIR, "cadre"),
    ]:
        if not source_dir.is_dir():
            continue
        for agent_file in sorted(source_dir.iterdir()):
            if agent_file.suffix not in (".md", ".yaml", ".yml"):
                continue
            name = agent_file.stem
            entry = {
                "name": name,
                "format": agent_file.suffix.lstrip("."),
                "source": source_label,
                "path": str(agent_file),
            }
            # claude location takes precedence
            if name not in seen or source_label == "claude":
                seen[name] = entry

    return sorted(seen.values(), key=lambda e: e["name"])


def install_from_url(url: str, dest_dir: Optional[Path] = None) -> Path:
    """Download an agent file from a URL and install it.

    Supports raw GitHub URLs and any direct link to a .md or .yaml file.

    Args:
        url:      Direct URL to the agent file.
        dest_dir: Installation directory.  Defaults to ~/.claude/agents/.

    Returns:
        Path to the installed file.

    Raises:
        ValueError:      If the URL does not point to a .md/.yaml file.
        urllib.error.URLError: On network errors.
        RuntimeError:    If the downloaded content fails validation.
    """
    target_dir = dest_dir or CLAUDE_AGENTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Derive filename from URL; convert GitHub blob URLs to raw URLs.
    raw_url = _normalize_github_url(url)
    filename = _filename_from_url(raw_url)

    if Path(filename).suffix not in (".md", ".yaml", ".yml"):
        raise ValueError(
            f"URL must point to a .md or .yaml file, got: {filename}"
        )

    print(f"Downloading {raw_url} ...")
    try:
        with urllib.request.urlopen(raw_url, timeout=30) as response:
            content = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise urllib.error.URLError(
            f"Failed to download agent from {raw_url}: {exc.reason}"
        ) from exc

    # Write to temp location, validate, then move into place.
    dest_path = target_dir / filename
    dest_path.write_text(content, encoding="utf-8")

    errors = validate_agent(dest_path)
    if errors:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded agent failed validation:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    print(f"Installed: {dest_path}")
    return dest_path


def install_from_file(path: Path, dest_dir: Optional[Path] = None) -> Path:
    """Copy a local agent file into the install directory.

    Args:
        path:     Path to the source .md or .yaml agent file.
        dest_dir: Installation directory.  Defaults to ~/.claude/agents/.

    Returns:
        Path to the installed file.

    Raises:
        FileNotFoundError: If the source file does not exist.
        ValueError:        If the file extension is not .md/.yaml.
        RuntimeError:      If the file fails validation.
    """
    source = Path(path).expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"Agent file not found: {source}")

    if source.suffix not in (".md", ".yaml", ".yml"):
        raise ValueError(
            f"Agent file must be .md or .yaml, got: {source.suffix}"
        )

    errors = validate_agent(source)
    if errors:
        raise RuntimeError(
            f"Agent file failed validation:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    target_dir = dest_dir or CLAUDE_AGENTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    dest_path = target_dir / source.name
    shutil.copy2(source, dest_path)
    print(f"Installed: {dest_path}")
    return dest_path


def validate_agent(path: Path) -> list[str]:
    """Validate an agent file for required structure.

    Checks differ by format:
    - .md files:   Must contain the required markdown headings.
    - .yaml files: Must contain the required top-level keys.

    Args:
        path: Path to the agent file.

    Returns:
        List of validation error strings.  Empty list means the file is valid.
    """
    path = Path(path)
    errors: list[str] = []

    if not path.exists():
        return [f"File does not exist: {path}"]

    if path.suffix == ".md":
        errors.extend(_validate_md_agent(path))
    elif path.suffix in (".yaml", ".yml"):
        errors.extend(_validate_yaml_agent(path))
    else:
        errors.append(f"Unsupported file extension: {path.suffix}")

    return errors


def uninstall(name: str, source_dir: Optional[Path] = None) -> bool:
    """Remove an installed agent by name.

    Searches ~/.claude/agents/ first, then ~/.cadre-ai/plugins/.

    Args:
        name:       Agent slug (with or without file extension).
        source_dir: Restrict search to this directory (optional).

    Returns:
        True if the agent was found and removed, False if not found.
    """
    stem = Path(name).stem  # strip extension if provided

    search_dirs: list[Path] = (
        [source_dir] if source_dir else [CLAUDE_AGENTS_DIR, CADRE_PLUGINS_DIR]
    )

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for ext in (".md", ".yaml", ".yml"):
            candidate = directory / f"{stem}{ext}"
            if candidate.exists():
                candidate.unlink()
                print(f"Removed: {candidate}")
                return True

    print(f"Agent not found: {name}")
    return False


def search_registry(query: str, registry_path: Optional[Path] = None) -> list[dict]:
    """Search the community plugin registry for agents matching query.

    Searches name, description, author, and tags fields (case-insensitive).

    Args:
        query:         Search string.
        registry_path: Path to a registry.json file.
                       Defaults to the bundled plugins/registry.json.

    Returns:
        List of matching registry entries (each is a dict).
        Returns an empty list if the registry file cannot be read or parsed.
    """
    reg_path = registry_path or BUNDLED_REGISTRY

    if not reg_path.exists():
        print(f"Registry not found: {reg_path}")
        return []

    try:
        entries: list[dict] = json.loads(reg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Failed to read registry: {exc}")
        return []

    q = query.lower()
    results = []

    for entry in entries:
        searchable = " ".join([
            entry.get("name", ""),
            entry.get("description", ""),
            entry.get("author", ""),
            " ".join(entry.get("tags", [])),
        ]).lower()

        if q in searchable:
            results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_github_url(url: str) -> str:
    """Convert a GitHub blob URL to a raw.githubusercontent.com URL."""
    # https://github.com/USER/REPO/blob/BRANCH/path/file.md
    # -> https://raw.githubusercontent.com/USER/REPO/BRANCH/path/file.md
    pattern = r"https://github\.com/([^/]+/[^/]+)/blob/(.+)"
    match = re.match(pattern, url)
    if match:
        repo = match.group(1)
        rest = match.group(2)
        return f"https://raw.githubusercontent.com/{repo}/{rest}"
    return url


def _filename_from_url(url: str) -> str:
    """Extract filename from the last path component of a URL."""
    return url.rstrip("/").split("/")[-1].split("?")[0]


def _validate_md_agent(path: Path) -> list[str]:
    """Validate a .md agent file."""
    errors: list[str] = []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Cannot read file: {exc}"]

    if not content.strip():
        return ["File is empty."]

    # Must start with a top-level heading (the agent name)
    lines = content.splitlines()
    if not lines or not lines[0].startswith("# "):
        errors.append("Missing top-level heading (# Agent Name) on line 1.")

    # Check required sections
    for section in _REQUIRED_MD_SECTIONS:
        if section not in content:
            errors.append(f"Missing required section: {section}")

    return errors


def _validate_yaml_agent(path: Path) -> list[str]:
    """Validate a .yaml agent file without importing PyYAML.

    Uses a simple line-by-line key scanner so this module stays
    stdlib-only.  For production-grade validation, PyYAML is preferred.
    """
    errors: list[str] = []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Cannot read file: {exc}"]

    if not content.strip():
        return ["File is empty."]

    # Collect top-level keys (lines that start at column 0 and match key: pattern)
    top_level_keys: set[str] = set()
    for line in content.splitlines():
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:", line)
        if match:
            top_level_keys.add(match.group(1))

    for key in _REQUIRED_YAML_KEYS:
        if key not in top_level_keys:
            errors.append(f"Missing required YAML key: '{key}'")

    return errors

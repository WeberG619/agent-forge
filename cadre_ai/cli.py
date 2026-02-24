"""
cadre CLI — entry point for the cadre-ai package.

Usage:
    cadre install                      Interactive installer
    cadre install --minimal            Non-interactive, core only
    cadre install --developer          Non-interactive, core + memory + hooks
    cadre install --power-user         Non-interactive, all components
    cadre uninstall                    Remove cadre from this system
    cadre version                      Show installed version
    cadre doctor                       Check system requirements
    cadre plugin install <name-or-url> Install a plugin from registry, URL, or local file
    cadre plugin list                  List installed agents
    cadre plugin search <query>        Search the community registry
    cadre plugin remove <name>         Remove an installed agent
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cadre_ai import __version__


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_install_script(name: str) -> Path | None:
    """Locate install.sh / uninstall.sh relative to this package."""
    # When installed via pip the shell scripts live in package data.
    # When running from a git clone they're at the repo root.
    candidates = [
        # git-clone layout: script is two levels up from cadre_ai/cli.py
        Path(__file__).parent.parent / name,
        # pip-installed layout: stored alongside this module
        Path(__file__).parent / name,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _run_install_script(script_path: Path, extra_args: list[str]) -> int:
    """Execute a bash script, inheriting the current terminal."""
    cmd = ["bash", str(script_path)] + extra_args
    try:
        result = subprocess.run(cmd)
        return result.returncode
    except KeyboardInterrupt:
        print("\nInstallation cancelled.")
        return 130
    except FileNotFoundError:
        print("Error: bash not found. Please install bash and try again.")
        return 1


def _check(label: str, found: bool, detail: str = "") -> bool:
    """Print a single doctor check line."""
    status = "OK  " if found else "FAIL"
    detail_str = f"  ({detail})" if detail else ""
    marker = "+" if found else "-"
    print(f"  [{marker}] {status}  {label}{detail_str}")
    return found


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    script = _find_install_script("install.sh")
    if script is None:
        print(
            "Error: install.sh not found.\n"
            "Make sure you installed cadre-ai from the full package or run from the git repo."
        )
        return 1

    extra: list[str] = []
    if args.tier == "minimal":
        extra = ["--minimal"]
    elif args.tier == "developer":
        extra = ["--ci"]
        # Override CI defaults to include memory and hooks
        os.environ.setdefault("CI_USER_NAME", os.environ.get("USER", "user"))
        os.environ["CADRE_DEVELOPER"] = "1"
    elif args.tier == "power-user":
        extra = ["--ci"]
        os.environ.setdefault("CI_USER_NAME", os.environ.get("USER", "user"))
        os.environ["CADRE_POWER_USER"] = "1"
    # else: no extra args — fully interactive

    return _run_install_script(script, extra)


def cmd_uninstall(args: argparse.Namespace) -> int:
    script = _find_install_script("uninstall.sh")
    if script is None:
        print(
            "Error: uninstall.sh not found.\n"
            "Please run 'bash uninstall.sh' manually from the cadre-ai repo directory."
        )
        return 1

    extra: list[str] = ["--yes"] if getattr(args, "yes", False) else []
    return _run_install_script(script, extra)


def cmd_version(args: argparse.Namespace) -> int:
    cadre_dir = os.environ.get("CADRE_DIR", "")
    print(f"cadre-ai  {__version__}")
    if cadre_dir:
        print(f"Installed at: {cadre_dir}")
    else:
        print("CADRE_DIR not set — run 'cadre install' to set up.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"cadre doctor — v{__version__}")
    print()

    all_ok = True

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 9)
    all_ok &= _check("Python >= 3.9", py_ok, py_ver)

    # Git
    git_path = shutil.which("git")
    if git_path:
        try:
            git_ver = subprocess.check_output(
                ["git", "--version"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            git_ver = "found"
    else:
        git_ver = ""
    all_ok &= _check("Git", bool(git_path), git_ver)

    # Claude Code (~/.claude/ directory)
    claude_dir = Path.home() / ".claude"
    all_ok &= _check("Claude Code (~/.claude/)", claude_dir.is_dir())

    # Node.js (optional — needed by some MCP servers)
    node_path = shutil.which("node")
    node_ver = ""
    if node_path:
        try:
            node_ver = subprocess.check_output(
                ["node", "--version"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            node_ver = "found"
    node_ok = _check("Node.js (optional — MCP servers)", bool(node_path), node_ver)
    # Node is optional so don't fail doctor for it, but do show the status.
    _ = node_ok

    # CADRE_DIR env var
    cadre_dir = os.environ.get("CADRE_DIR", "")
    cadre_dir_ok = bool(cadre_dir) and Path(cadre_dir).is_dir()
    all_ok &= _check("CADRE_DIR set and exists", cadre_dir_ok, cadre_dir or "not set")

    # pyyaml (core dependency)
    try:
        import yaml  # noqa: F401
        yaml_ok = True
        import importlib.metadata
        try:
            yaml_ver = importlib.metadata.version("pyyaml")
        except Exception:
            yaml_ver = "installed"
    except ImportError:
        yaml_ok = False
        yaml_ver = ""
    all_ok &= _check("pyyaml (core dependency)", yaml_ok, yaml_ver)

    # fastembed (optional — memory)
    try:
        import fastembed  # noqa: F401
        fe_ok = True
        fe_detail = "installed"
    except ImportError:
        fe_ok = False
        fe_detail = "not installed — run: pip install cadre-ai[memory]"
    _check("fastembed (optional — memory)", fe_ok, fe_detail)

    # edge-tts (optional — voice)
    try:
        import edge_tts  # noqa: F401
        tts_ok = True
        tts_detail = "installed"
    except ImportError:
        tts_ok = False
        tts_detail = "not installed — run: pip install cadre-ai[voice]"
    _check("edge-tts (optional — voice)", tts_ok, tts_detail)

    print()
    if all_ok:
        print("All required checks passed. Cadre is ready.")
    else:
        print("Some required checks failed. Run 'cadre install' to fix setup.")
    return 0 if all_ok else 1


def cmd_plugin(args: argparse.Namespace) -> int:
    """Plugin sub-commands — install, list, search, remove."""
    # Import here so the CLI remains usable even if plugins.py has an issue.
    from cadre_ai import plugins

    if args.plugin_cmd == "install":
        return _plugin_install(args, plugins)

    if args.plugin_cmd == "list":
        return _plugin_list(plugins)

    if args.plugin_cmd == "search":
        return _plugin_search(args, plugins)

    if args.plugin_cmd == "remove":
        return _plugin_remove(args, plugins)

    print(f"Unknown plugin sub-command: {args.plugin_cmd}")
    return 1


def _plugin_install(args: argparse.Namespace, plugins) -> int:  # type: ignore[type-arg]
    """Handle `cadre plugin install <name-or-url-or-path>`."""
    import urllib.error

    target: str = args.plugin_name

    # --- Local file path ---
    local = Path(target).expanduser()
    if local.exists():
        try:
            installed = plugins.install_from_file(local)
            print(f"Installed '{installed.stem}' from local file.")
            return 0
        except (ValueError, RuntimeError) as exc:
            print(f"Error: {exc}")
            return 1

    # --- URL (http / https) ---
    if target.startswith("http://") or target.startswith("https://"):
        try:
            installed = plugins.install_from_url(target)
            print(f"Installed '{installed.stem}' from URL.")
            return 0
        except (ValueError, RuntimeError, urllib.error.URLError) as exc:
            print(f"Error: {exc}")
            return 1

    # --- Registry name ---
    matches = plugins.search_registry(target)
    # Filter for exact name match first, then any match.
    exact = [m for m in matches if m["name"] == target]
    entry = exact[0] if exact else (matches[0] if matches else None)

    if entry is None:
        print(
            f"Plugin '{target}' not found in registry.\n"
            "Use a URL or local file path, or run 'cadre plugin search <query>' "
            "to browse available plugins."
        )
        return 1

    print(f"Found in registry: {entry['name']} v{entry['version']} by {entry['author']}")
    print(f"  {entry['description']}")
    try:
        installed = plugins.install_from_url(entry["url"])
        print(f"Installed '{installed.stem}' successfully.")
        return 0
    except (ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(f"Error: {exc}")
        return 1


def _plugin_list(plugins) -> int:  # type: ignore[type-arg]
    """Handle `cadre plugin list`."""
    agents = plugins.list_installed()

    if not agents:
        print("No agents installed.")
        print(
            "Run 'cadre plugin search <query>' to discover community plugins,\n"
            "or 'cadre plugin install <name-or-url>' to install one."
        )
        return 0

    # Column widths
    name_w = max(len(a["name"]) for a in agents)
    fmt_w = 4  # "yaml" / "md"

    header = f"  {'NAME':<{name_w}}  {'FMT':<{fmt_w}}  SOURCE   PATH"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for agent in agents:
        print(
            f"  {agent['name']:<{name_w}}  "
            f"{agent['format']:<{fmt_w}}  "
            f"{agent['source']:<8} "
            f"{agent['path']}"
        )

    print(f"\n  {len(agents)} agent(s) installed.")
    return 0


def _plugin_search(args: argparse.Namespace, plugins) -> int:  # type: ignore[type-arg]
    """Handle `cadre plugin search <query>`."""
    query: str = args.query
    results = plugins.search_registry(query)

    if not results:
        print(f"No plugins found matching '{query}'.")
        print("Try a broader search term or visit https://github.com/cadre-community/agents")
        return 0

    print(f"Found {len(results)} plugin(s) matching '{query}':\n")
    for entry in results:
        tags = ", ".join(entry.get("tags", []))
        print(f"  {entry['name']}  v{entry['version']}  by {entry['author']}")
        print(f"    {entry['description']}")
        if tags:
            print(f"    Tags: {tags}")
        print(f"    Install: cadre plugin install {entry['name']}")
        print()

    return 0


def _plugin_remove(args: argparse.Namespace, plugins) -> int:  # type: ignore[type-arg]
    """Handle `cadre plugin remove <name>`."""
    name: str = args.plugin_name
    removed = plugins.uninstall(name)
    return 0 if removed else 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadre",
        description="cadre-ai — Agent framework for Claude Code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cadre install                              # Interactive setup wizard\n"
            "  cadre install --minimal                    # Core only, no prompts\n"
            "  cadre install --developer                  # Core + memory + hooks\n"
            "  cadre install --power-user                 # All components\n"
            "  cadre doctor                               # Check system requirements\n"
            "  cadre version                              # Show version info\n"
            "  cadre plugin list                          # List installed agents\n"
            "  cadre plugin search docker                 # Search community registry\n"
            "  cadre plugin install docker-specialist     # Install from registry\n"
            "  cadre plugin install ./my-agent.md         # Install local file\n"
            "  cadre plugin remove docker-specialist      # Remove an agent\n"
        ),
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"cadre-ai {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # -- install --
    install_parser = sub.add_parser(
        "install",
        help="Install cadre into the current user's Claude Code environment.",
        description=(
            "Runs the cadre installer. Without flags it launches the interactive wizard.\n"
            "Use a tier flag for non-interactive (CI / scripted) installs."
        ),
    )
    tier_group = install_parser.add_mutually_exclusive_group()
    tier_group.add_argument(
        "--minimal",
        dest="tier",
        action="store_const",
        const="minimal",
        help="Non-interactive: install core framework only (no memory, voice, or hooks).",
    )
    tier_group.add_argument(
        "--developer",
        dest="tier",
        action="store_const",
        const="developer",
        help="Non-interactive: install core + memory MCP + safety hooks.",
    )
    tier_group.add_argument(
        "--power-user",
        dest="tier",
        action="store_const",
        const="power-user",
        help="Non-interactive: install all components.",
    )
    install_parser.set_defaults(tier=None)

    # -- uninstall --
    uninstall_parser = sub.add_parser(
        "uninstall",
        help="Remove cadre from this system.",
    )
    uninstall_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt.",
    )

    # -- version --
    sub.add_parser(
        "version",
        help="Show cadre version and installation path.",
    )

    # -- doctor --
    sub.add_parser(
        "doctor",
        help="Check system requirements (Python, Git, Claude Code, Node.js, dependencies).",
    )

    # -- plugin --
    plugin_parser = sub.add_parser(
        "plugin",
        help="Manage cadre plugins.",
        description=(
            "Install, list, search, and remove cadre agent plugins.\n\n"
            "Examples:\n"
            "  cadre plugin list\n"
            "  cadre plugin search docker\n"
            "  cadre plugin install docker-specialist\n"
            "  cadre plugin install https://github.com/you/agents/blob/main/agent.md\n"
            "  cadre plugin install ./my-agent.md\n"
            "  cadre plugin remove docker-specialist\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_cmd", metavar="<sub-command>")
    plugin_sub.required = True

    plugin_install = plugin_sub.add_parser(
        "install",
        help="Install a plugin from the registry, a URL, or a local file.",
        description=(
            "Install a cadre plugin.\n\n"
            "  By registry name:  cadre plugin install docker-specialist\n"
            "  By URL:            cadre plugin install https://github.com/.../agent.md\n"
            "  By local path:     cadre plugin install ./my-agent.md\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    plugin_install.add_argument(
        "plugin_name",
        metavar="<name-or-url-or-path>",
        help="Registry name, GitHub/raw URL, or local file path.",
    )

    plugin_sub.add_parser(
        "list",
        help="List all installed agents (~/.claude/agents/ and ~/.cadre-ai/plugins/).",
    )

    plugin_search = plugin_sub.add_parser(
        "search",
        help="Search the community plugin registry.",
    )
    plugin_search.add_argument(
        "query",
        metavar="<query>",
        help="Search term (matches name, description, author, and tags).",
    )

    plugin_remove = plugin_sub.add_parser(
        "remove",
        help="Remove an installed agent by name.",
    )
    plugin_remove.add_argument(
        "plugin_name",
        metavar="<name>",
        help="Agent slug to remove (e.g. docker-specialist).",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "version": cmd_version,
        "doctor": cmd_doctor,
        "plugin": cmd_plugin,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
bench_agents.py
===============
Benchmarks for the cadre-ai agent system.

Tests: parse time for all agent definitions (.md + .yaml),
schema validation (required header fields), and dispatch routing
overhead simulation (keyword-based routing across all agents).

No live Claude API calls are made.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BENCH_DIR = Path(__file__).parent
_PROJECT_ROOT = _BENCH_DIR.parent
_AGENTS_DIR = _PROJECT_ROOT / "agents"


# ---------------------------------------------------------------------------
# Agent definition parsing
# ---------------------------------------------------------------------------

# Required fields we expect in each agent definition
_REQUIRED_MD_FIELDS = ["Squad", "Role"]
_REQUIRED_YAML_FIELDS = ["name", "description"]

# Routing keywords that should map to agents — simulates a dispatcher
# mapping: keyword -> expected agent file stem
_ROUTING_TABLE = {
    "python": "python-engineer",
    "script": "python-engineer",
    "architecture": "code-architect",
    "design": "code-architect",
    "csharp": "csharp-developer",
    "c#": "csharp-developer",
    ".net": "csharp-developer",
    "test": "test-runner",
    "testing": "test-runner",
    "analyze": "code-analyzer",
    "analysis": "code-analyzer",
    "deploy": "devops-agent",
    "devops": "devops-agent",
    "docker": "devops-agent",
    "fullstack": "fullstack-dev",
    "frontend": "fullstack-dev",
    "backend": "fullstack-dev",
    "ml": "ml-engineer",
    "machine learning": "ml-engineer",
    "market": "market-analyst",
    "research": "market-analyst",
    "simplify": "code-simplifier",
    "refactor": "code-simplifier",
    "scrape": "doc-scraper",
    "documentation": "doc-scraper",
    "orchestrate": "orchestrator",
    "coordinate": "orchestrator",
    "build agent": "agent-builder",
    "prompt": "prompt-engineer",
    "project": "project-manager",
    "planning": "project-manager",
    "learn": "learning-agent",
    "tech": "tech-scout",
    "scout": "tech-scout",
}

# Sample user requests for routing simulation
_SAMPLE_REQUESTS = [
    "Write a python script to parse JSON files",
    "Design the architecture for a new microservice",
    "Fix the C# compilation error in the Revit bridge",
    "Run the test suite for the memory module",
    "Analyze the performance of the database queries",
    "Deploy the updated Docker container to staging",
    "Build a fullstack dashboard with React",
    "Train an ML model for prediction",
    "Research the current market for AI tooling",
    "Simplify this overly complex function",
    "Scrape the API documentation",
    "Orchestrate these three parallel tasks",
    "Build a new agent for Slack integration",
    "Write a system prompt for the memory agent",
    "Create a project plan for Q2",
    "Learn from this correction and update memory",
    "Scout for new Python frameworks",
    "Check git status and create a PR",
    "Write unit tests for the sense engine",
    "Refactor the legacy code module",
]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_md_agent(path: Path) -> dict:
    """
    Parse a markdown agent definition.
    Extracts YAML-like header fields from lines like '**Squad:** Development'.
    """
    text = path.read_text(encoding="utf-8")
    fields = {}

    # Match bold-label patterns: **Field:** Value  or  > **Field:** Value
    pattern = re.compile(r"\*\*([^*]+)\*\*[:\s]+(.+)")
    for line in text.splitlines()[:40]:  # Only scan the preamble
        m = pattern.search(line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            fields[key] = val

    # Also check for H1 name
    h1 = re.search(r"^#\s+(.+)", text, re.MULTILINE)
    if h1:
        fields["_name"] = h1.group(1).strip()

    fields["_path"] = str(path)
    fields["_type"] = "md"
    fields["_char_count"] = len(text)
    fields["_line_count"] = text.count("\n")
    return fields


def _parse_yaml_agent(path: Path) -> dict:
    """
    Parse a YAML agent definition without PyYAML.
    Extracts top-level key: value pairs via regex.
    """
    text = path.read_text(encoding="utf-8")
    fields = {}

    # Simple top-level key: value extraction (no nesting)
    pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)", re.MULTILINE)
    for m in pattern.finditer(text):
        key = m.group(1)
        val = m.group(2).strip().strip('"').strip("'")
        if key not in fields:  # First occurrence wins
            fields[key] = val

    fields["_path"] = str(path)
    fields["_type"] = "yaml"
    fields["_char_count"] = len(text)
    fields["_line_count"] = text.count("\n")
    return fields


def _validate_agent(parsed: dict) -> list[str]:
    """
    Validate a parsed agent definition.
    Returns list of validation errors (empty = valid).
    """
    errors = []
    agent_type = parsed.get("_type", "md")

    if agent_type == "md":
        for field in _REQUIRED_MD_FIELDS:
            if field not in parsed:
                errors.append(f"Missing required field: {field}")
        if parsed.get("_char_count", 0) < 100:
            errors.append("Definition suspiciously short (< 100 chars)")

    elif agent_type == "yaml":
        for field in _REQUIRED_YAML_FIELDS:
            if field not in parsed:
                errors.append(f"Missing required field: {field}")
        if parsed.get("_char_count", 0) < 20:
            errors.append("Definition suspiciously short (< 20 chars)")

    return errors


def _route_request(request: str, agents: list[dict]) -> Optional[str]:
    """
    Simulate keyword-based dispatch routing.
    Returns the stem of the matched agent, or None.
    """
    request_lower = request.lower()

    # Check routing table first
    for keyword, target_stem in _ROUTING_TABLE.items():
        if keyword in request_lower:
            return target_stem

    # Fallback: scan agent fields for keyword overlap
    request_words = set(re.findall(r"\b\w+\b", request_lower))
    best_agent = None
    best_score = 0

    for agent in agents:
        name = Path(agent.get("_path", "")).stem
        role = agent.get("Role", agent.get("description", "")).lower()
        squad = agent.get("Squad", "").lower()
        combined = f"{name} {role} {squad}"
        agent_words = set(re.findall(r"\b\w+\b", combined))
        score = len(request_words & agent_words)
        if score > best_score:
            best_score = score
            best_agent = name

    return best_agent if best_score > 0 else None


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def bench_parse_all(verbose: bool = False) -> dict:
    """Time parsing of all agent definition files."""
    md_files = sorted(_AGENTS_DIR.glob("*.md"))
    yaml_files = sorted(_AGENTS_DIR.glob("*.yaml"))
    all_files = md_files + yaml_files

    if not all_files:
        return {"error": f"No agent files found in {_AGENTS_DIR}", "agents": []}

    agents = []
    t0 = time.perf_counter()

    for path in all_files:
        if path.suffix == ".md":
            agents.append(_parse_md_agent(path))
        elif path.suffix in (".yaml", ".yml"):
            agents.append(_parse_yaml_agent(path))

    elapsed = time.perf_counter() - t0

    return {
        "total_files": len(all_files),
        "md_files": len(md_files),
        "yaml_files": len(yaml_files),
        "elapsed_s": round(elapsed, 6),
        "per_file_ms": round(elapsed / len(all_files) * 1000, 4),
        "total_chars": sum(a.get("_char_count", 0) for a in agents),
        "total_lines": sum(a.get("_line_count", 0) for a in agents),
        "agents": agents,
    }


def bench_validate_schemas(agents: list[dict]) -> dict:
    """Validate all parsed agent definitions against required schemas."""
    t0 = time.perf_counter()

    validation_results = {}
    total_errors = 0
    valid_count = 0

    for agent in agents:
        stem = Path(agent.get("_path", "unknown")).stem
        errors = _validate_agent(agent)
        validation_results[stem] = errors
        if errors:
            total_errors += len(errors)
        else:
            valid_count += 1

    elapsed = time.perf_counter() - t0

    return {
        "total_agents": len(agents),
        "valid": valid_count,
        "invalid": len(agents) - valid_count,
        "total_errors": total_errors,
        "elapsed_s": round(elapsed, 6),
        "per_agent_ms": round(elapsed / max(len(agents), 1) * 1000, 6),
        "results": validation_results,
    }


def bench_dispatch_routing(agents: list[dict], requests: list[str], runs: int = 10) -> dict:
    """
    Simulate dispatch routing overhead.
    Routes each request `runs` times and measures total + per-call time.
    """
    all_requests = requests * runs
    total_calls = len(all_requests)
    routed = 0
    unrouted = []

    t0 = time.perf_counter()
    for req in all_requests:
        result = _route_request(req, agents)
        if result:
            routed += 1
        else:
            if req not in unrouted:
                unrouted.append(req)
    elapsed = time.perf_counter() - t0

    # Single-pass timing for per-call stat
    timings = []
    for req in requests:
        t_req = time.perf_counter()
        _route_request(req, agents)
        timings.append(time.perf_counter() - t_req)

    avg_per_call = sum(timings) / len(timings)

    return {
        "total_route_calls": total_calls,
        "routed": routed,
        "unrouted_unique": unrouted,
        "route_success_rate": round(routed / total_calls, 4),
        "elapsed_s": round(elapsed, 6),
        "ops_per_s": round(total_calls / elapsed),
        "per_call_us": round(avg_per_call * 1_000_000, 2),
    }


def bench_agent_inventory() -> dict:
    """Count and categorize all agent files without timing."""
    md_files = list(_AGENTS_DIR.glob("*.md"))
    yaml_files = list(_AGENTS_DIR.glob("*.yaml"))

    stems = sorted(
        [p.stem for p in md_files + yaml_files]
    )

    # Identify duplicates (same stem, different extension)
    all_stems = [p.stem for p in md_files + yaml_files]
    seen = {}
    for s in all_stems:
        seen[s] = seen.get(s, 0) + 1
    duplicates = [s for s, c in seen.items() if c > 1]

    return {
        "md_count": len(md_files),
        "yaml_count": len(yaml_files),
        "total": len(md_files) + len(yaml_files),
        "agent_stems": stems,
        "duplicate_stems": duplicates,
        "agents_dir": str(_AGENTS_DIR),
    }


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------

def run(verbose: bool = False) -> list[dict]:
    """Run all agent benchmarks. Returns list of result dicts."""
    results = []

    # --- Inventory ---
    inventory = bench_agent_inventory()
    results.append({
        "benchmark": "agent_inventory",
        "label": f"Inventory {inventory['total']} agent files",
        "total": inventory["total"],
        "md": inventory["md_count"],
        "yaml": inventory["yaml_count"],
        "detail": inventory,
    })
    if verbose:
        print(f"  [inventory] {inventory['total']} agents ({inventory['md_count']} .md, {inventory['yaml_count']} .yaml)")
        if inventory["duplicate_stems"]:
            print(f"    Duplicates: {inventory['duplicate_stems']}")

    if inventory["total"] == 0:
        results.append({"benchmark": "error", "error": f"No agent files in {_AGENTS_DIR}"})
        return results

    # --- Parse all ---
    parse_res = bench_parse_all(verbose=verbose)
    agents = parse_res.pop("agents", [])
    results.append({
        "benchmark": "parse_all_agents",
        "label": f"Parse {parse_res['total_files']} agent definitions",
        "elapsed_s": parse_res["elapsed_s"],
        "per_file_ms": parse_res["per_file_ms"],
        "detail": parse_res,
    })
    if verbose:
        print(
            f"  [parse_all] {parse_res['elapsed_s']*1000:.2f}ms total | "
            f"{parse_res['per_file_ms']:.3f}ms/file | "
            f"{parse_res['total_chars']:,} chars | "
            f"{parse_res['total_lines']:,} lines"
        )

    # --- Repeated parse (cold vs warm read) ---
    parse_times = []
    for _ in range(5):
        t0 = time.perf_counter()
        bench_parse_all()
        parse_times.append(time.perf_counter() - t0)

    cold = parse_times[0]
    warm_avg = sum(parse_times[1:]) / len(parse_times[1:])
    results.append({
        "benchmark": "parse_cold_vs_warm",
        "label": "Parse cold vs warm (OS file cache)",
        "cold_ms": round(cold * 1000, 3),
        "warm_avg_ms": round(warm_avg * 1000, 3),
        "speedup": round(cold / max(warm_avg, 1e-9), 2),
        "detail": {"cold_s": cold, "warm_avg_s": warm_avg, "runs": 5},
    })
    if verbose:
        print(f"  [cold_vs_warm] cold={cold*1000:.2f}ms | warm_avg={warm_avg*1000:.2f}ms | speedup={cold/max(warm_avg,1e-9):.1f}x")

    # --- Schema validation ---
    val_res = bench_validate_schemas(agents)
    results.append({
        "benchmark": "schema_validation",
        "label": f"Validate {val_res['total_agents']} agent schemas",
        "elapsed_s": val_res["elapsed_s"],
        "valid": val_res["valid"],
        "invalid": val_res["invalid"],
        "total_errors": val_res["total_errors"],
        "detail": val_res,
    })
    if verbose:
        print(
            f"  [schema] {val_res['valid']}/{val_res['total_agents']} valid | "
            f"{val_res['invalid']} invalid | "
            f"{val_res['total_errors']} total errors | "
            f"{val_res['per_agent_ms']:.4f}ms/agent"
        )
        for stem, errs in val_res["results"].items():
            if errs:
                print(f"    INVALID [{stem}]: {errs}")

    # --- Dispatch routing ---
    routing_res = bench_dispatch_routing(agents, _SAMPLE_REQUESTS, runs=10)
    results.append({
        "benchmark": "dispatch_routing",
        "label": f"Route {routing_res['total_route_calls']} requests across {len(agents)} agents",
        "elapsed_s": routing_res["elapsed_s"],
        "ops_per_s": routing_res["ops_per_s"],
        "per_call_us": routing_res["per_call_us"],
        "route_success_rate": routing_res["route_success_rate"],
        "detail": routing_res,
    })
    if verbose:
        print(
            f"  [routing] {routing_res['ops_per_s']:,} routes/s | "
            f"{routing_res['per_call_us']:.1f}us/call | "
            f"success={routing_res['route_success_rate']:.1%}"
        )
        if routing_res["unrouted_unique"]:
            print(f"    Unrouted: {routing_res['unrouted_unique']}")

    return results


if __name__ == "__main__":
    print("Running agent benchmarks standalone...\n")
    results = run(verbose=True)
    print(f"\nDone. {len(results)} benchmark results collected.")

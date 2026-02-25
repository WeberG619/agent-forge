"""
Injection helper for Claude Code sub-agents.

Reads the kernel.md and seeds.json, returns a formatted string
you can prepend to any agent's prompt to give it common sense.

Usage in CLAUDE.md or agent config:
    import inject
    agent_prompt = inject.get_kernel() + "\n\n" + your_agent_prompt

Or from CLI:
    python inject.py > /tmp/kernel_prompt.txt
    python inject.py --with-seeds > /tmp/full_prompt.txt
"""

import json
from pathlib import Path

HERE = Path(__file__).parent


def get_kernel() -> str:
    """Return the common sense kernel prompt."""
    kernel_path = HERE / "kernel.md"
    return kernel_path.read_text()


def get_seeds_as_prompt() -> str:
    """Format seed corrections as a prompt-injectable block."""
    seeds_path = HERE / "seeds.json"
    if not seeds_path.exists():
        return ""

    data = json.loads(seeds_path.read_text())
    corrections = data.get("corrections", [])

    lines = ["## Pre-Loaded Experience (Known Mistakes to Avoid)", ""]

    for c in corrections:
        severity_icon = {"critical": "!!!", "high": "!!", "medium": "!", "low": "~"}.get(
            c["severity"], "!"
        )
        lines.append(f"### [{severity_icon}] {c['domain'].upper()}: {c['what_went_wrong']}")
        lines.append(f"**Do instead:** {c['correct_approach']}")
        lines.append(f"**Watch for:** {c['detection']}")
        lines.append("")

    return "\n".join(lines)


def get_full_injection(include_seeds: bool = True) -> str:
    """
    Get the complete common sense injection.
    Prepend this to any agent's system prompt.
    """
    parts = [get_kernel()]
    if include_seeds:
        parts.append(get_seeds_as_prompt())
    return "\n\n---\n\n".join(parts)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate common sense prompt injection")
    parser.add_argument("--with-seeds", action="store_true", help="Include seed corrections")
    parser.add_argument("--kernel-only", action="store_true", help="Only the kernel, no seeds")
    parser.add_argument("--seeds-only", action="store_true", help="Only the seeds, no kernel")
    args = parser.parse_args()

    if args.seeds_only:
        print(get_seeds_as_prompt())
    elif args.kernel_only:
        print(get_kernel())
    else:
        print(get_full_injection(include_seeds=args.with_seeds))


if __name__ == "__main__":
    main()

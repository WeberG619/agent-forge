#!/usr/bin/env python3
"""
Pre-commit guard for Claude Code.
Runs as a PreToolUse hook on Bash calls.
Checks staged files for sensitive data before git commit operations.
"""

import os
import re
import subprocess
import sys


def is_git_commit():
    """Check if the current tool input is a git commit command."""
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
    return bool(re.search(r'\bgit\s+commit\b', tool_input))


def get_staged_files():
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
            capture_output=True, text=True, timeout=5
        )
        return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
    except Exception:
        return []


def check_sensitive_data(files):
    """Check staged files for sensitive data patterns."""
    issues = []
    patterns = [
        (r'password["\']?\s*[:=]\s*["\'][^"\']+["\']', "hardcoded password"),
        (r'api[_-]?key["\']?\s*[:=]\s*["\'][^"\']+["\']', "API key"),
        (r'secret["\']?\s*[:=]\s*["\'][^"\']+["\']', "secret value"),
        (r'token["\']?\s*[:=]\s*["\'][^"\']+["\']', "token value"),
        (r'aws[_-]?access', "AWS credentials"),
        (r'private[_-]?key', "private key reference"),
    ]

    sensitive_files = ['.env', 'credentials.json', '.secret', 'token.json']

    for f in files:
        basename = os.path.basename(f).lower()
        if basename in sensitive_files:
            issues.append(f"BLOCKED: Sensitive file staged: {f}")
            continue

        try:
            result = subprocess.run(
                ['git', 'diff', '--cached', '--', f],
                capture_output=True, text=True, timeout=5
            )
            diff_content = result.stdout
            for pattern, desc in patterns:
                if re.search(pattern, diff_content, re.IGNORECASE):
                    issues.append(f"WARNING: Potential {desc} in {f}")
        except Exception:
            pass

    return issues


def main():
    if not is_git_commit():
        sys.exit(0)

    files = get_staged_files()
    if not files:
        sys.exit(0)

    issues = check_sensitive_data(files)
    blocked = [i for i in issues if i.startswith("BLOCKED")]

    if blocked:
        print("Pre-commit guard: BLOCKED")
        for issue in issues:
            print(f"  {issue}")
        sys.exit(1)

    if issues:
        print("Pre-commit guard: warnings found (proceeding)")
        for issue in issues:
            print(f"  {issue}")

    sys.exit(0)


if __name__ == "__main__":
    main()

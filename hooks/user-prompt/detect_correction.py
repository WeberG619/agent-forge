#!/usr/bin/env python3
"""
UserPromptSubmit Hook: Detect when user is correcting Claude.

This hook fires on every user message and checks if the user appears
to be correcting Claude. If detected, it outputs a reminder for Claude
to capture the correction using memory_store_correction.

Exit codes:
- 0: Success (output shown in transcript)
"""

import json
import sys
import re

# Correction patterns - phrases that indicate user is correcting Claude
CORRECTION_PATTERNS = [
    r"no[,.]?\s*that'?s\s*(wrong|incorrect|not\s*right)",
    r"actually[,.]",
    r"no[,.]?\s*i\s*meant",
    r"i\s*told\s*you",
    r"not\s*what\s*i",
    r"you\s*forgot",
    r"that'?s\s*not\s*(right|correct|how)",
    r"wrong\s*(approach|way)",
    r"you\s*should\s*have",
    r"the\s*correct\s*way",
    r"you\s*made\s*a\s*mistake",
    r"you\s*misunderstood",
    r"let\s*me\s*clarify",
    r"don'?t\s*do\s*that",
    r"stop\s*doing\s*that",
    r"that'?s\s*not\s*what\s*i\s*(asked|wanted|said)",
    r"i\s*already\s*told\s*you",
    r"you'?re\s*(wrong|mistaken|confused)",
]


def detect_correction_intent(message: str) -> tuple:
    """Detect if the user message appears to be a correction."""
    if not message:
        return False, []

    message_lower = message.lower()
    matched = []

    for pattern in CORRECTION_PATTERNS:
        if re.search(pattern, message_lower):
            matched.append(pattern)

    # Also check for explicit correction keywords in short messages
    explicit_keywords = ["wrong", "incorrect", "mistake", "error", "fix this", "not right"]
    for keyword in explicit_keywords:
        if keyword in message_lower and len(message) < 200:
            if keyword not in matched:
                matched.append(f"keyword:{keyword}")

    return len(matched) > 0, matched


def main():
    # Read hook input from stdin
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            sys.exit(0)
        hook_input = json.loads(stdin_data)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    user_prompt = hook_input.get("user_prompt", "")

    if not user_prompt:
        sys.exit(0)

    is_correction, patterns = detect_correction_intent(user_prompt)

    if is_correction:
        output = {
            "type": "correction_detected",
            "message": "CORRECTION DETECTED in user message",
            "instruction": "If this is indeed a correction, use memory_store_correction() to capture: what you did wrong, why it was wrong, and the correct approach.",
            "matched_patterns": patterns[:3],
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()

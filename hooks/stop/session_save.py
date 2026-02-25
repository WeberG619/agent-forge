#!/usr/bin/env python3
"""
Stop Hook - Save session state when Claude Code exits.
Stores a session summary in memory for resume capability.
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path


def main():
    # Read hook input from stdin
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            sys.exit(0)
        json.loads(stdin_data)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    # Save basic session info
    install_dir = os.environ.get("CADRE_DIR", str(Path.home() / ".cadre-ai"))
    session_file = Path(install_dir) / "session_state.json"

    try:
        session_state = {
            "ended_at": datetime.now().isoformat(),
            "cwd": os.getcwd(),
        }

        session_file.parent.mkdir(parents=True, exist_ok=True)
        with open(session_file, "w") as f:
            json.dump(session_state, f, indent=2)

    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()

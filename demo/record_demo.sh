#!/usr/bin/env bash
# record_demo.sh — Record an asciinema terminal demo of Cadre AI
#
# Requirements:
#   asciinema   https://asciinema.org/docs/installation
#   expect      sudo apt install expect  (or brew install expect)
#
# Usage:
#   chmod +x record_demo.sh
#   ./record_demo.sh
#
# Output:
#   demo/cadre-demo.cast   (asciinema v2 format)
#
# Convert to GIF:
#   agg cadre-demo.cast cadre-demo.gif
#     — install agg: https://github.com/asciinema/agg
#
# Convert to SVG animation:
#   svg-term --in cadre-demo.cast --out cadre-demo.svg --window
#     — install: npm install -g svg-term-cli
#
# Convert to MP4 (for YouTube / X):
#   agg cadre-demo.cast cadre-demo.gif && ffmpeg -i cadre-demo.gif cadre-demo.mp4

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="${SCRIPT_DIR}/cadre-demo.cast"
DEMO_SCRIPT="${SCRIPT_DIR}/_demo_session.exp"

# ── Verify tools ──────────────────────────────────────────────────────────────
if ! command -v asciinema &>/dev/null; then
  echo "ERROR: asciinema not found. Install it: https://asciinema.org/docs/installation"
  exit 1
fi

if ! command -v expect &>/dev/null; then
  echo "ERROR: expect not found. Install it: sudo apt install expect"
  exit 1
fi

# ── Write the expect script ───────────────────────────────────────────────────
cat > "${DEMO_SCRIPT}" << 'EXPECT_SCRIPT'
#!/usr/bin/expect -f
#
# Cadre AI — demo terminal session
# Simulates three real workflows:
#   1. Health check + minimal install
#   2. /prime on a new project + memory recall in next session
#   3. Common sense engine blocking a dangerous action + correction capture

set timeout 30
set send_human {0.05 0.15 0.01 0.02 0.08}   ;# realistic typing speed

# ── helpers ──────────────────────────────────────────────────────────────────
proc type_line {text} {
  send -h "$text"
  after 300
  send "\r"
  after 800
}

proc pause {ms} {
  after $ms
}

proc banner {text} {
  send_user "\n\033\[1;36m── $text ──\033\[0m\n\n"
  after 600
}

# ── start shell ───────────────────────────────────────────────────────────────
spawn bash --norc --noprofile
expect "$ "

# ─────────────────────────────────────────────────────────────────────────────
# SCENE 1: System health check
# ─────────────────────────────────────────────────────────────────────────────
banner "Scene 1 — cadre doctor"

send_user "\033\[0;90m# Check that Cadre is correctly installed\033\[0m\n"
pause 500

type_line "cadre doctor"

expect "$ "
pause 1200

# ─────────────────────────────────────────────────────────────────────────────
# SCENE 2: Install (minimal tier)
# ─────────────────────────────────────────────────────────────────────────────
banner "Scene 2 — cadre install --minimal"

send_user "\033\[0;90m# Install Cadre (minimal tier — no desktop automation)\033\[0m\n"
pause 500

type_line "cadre install --minimal --yes"

expect "$ "
pause 1500

# ─────────────────────────────────────────────────────────────────────────────
# SCENE 3: /prime on a project
# ─────────────────────────────────────────────────────────────────────────────
banner "Scene 3 — /prime on a new project"

send_user "\033\[0;90m# Change to a project directory and run /prime\033\[0m\n"
pause 500

type_line "cd ~/projects/my-fastapi-app"
expect "$ "
pause 400

type_line "claude"
expect ">"
pause 800

send_user "\033\[0;90m# Slash command: prime the project context\033\[0m\n"
pause 400
type_line "/prime"

expect ">"
pause 2000

type_line "exit"
expect "$ "
pause 800

# ─────────────────────────────────────────────────────────────────────────────
# SCENE 4: Memory recall in a NEW session
# ─────────────────────────────────────────────────────────────────────────────
banner "Scene 4 — memory recall in next session"

send_user "\033\[0;90m# A brand-new Claude Code session — no project context loaded yet\033\[0m\n"
pause 600

type_line "claude"
expect ">"
pause 800

send -h "What do we know about my-fastapi-app?"
after 300
send "\r"
expect ">"
pause 2500

type_line "exit"
expect "$ "
pause 800

# ─────────────────────────────────────────────────────────────────────────────
# SCENE 5: Common sense engine + correction capture
# ─────────────────────────────────────────────────────────────────────────────
banner "Scene 5 — common sense block + correction"

send_user "\033\[0;90m# Dangerous action — common sense engine intervenes\033\[0m\n"
pause 600

type_line "claude"
expect ">"
pause 800

send -h "Delete all .log files in /var/log recursively"
after 300
send "\r"
expect ">"
pause 2500

send_user "\033\[0;90m# User corrects the agent — correction is captured automatically\033\[0m\n"
pause 600

send -h "Don't delete system logs — only delete logs inside ~/projects/"
after 300
send "\r"
expect ">"
pause 2500

type_line "exit"
expect "$ "

# done
send_user "\n\033\[1;32m Demo recording complete.\033\[0m\n"
EXPECT_SCRIPT

chmod +x "${DEMO_SCRIPT}"

# ── Record ────────────────────────────────────────────────────────────────────
echo ""
echo "Recording Cadre AI demo to: ${OUTPUT}"
echo "Press Ctrl+C to stop early."
echo ""

asciinema rec \
  --command "expect ${DEMO_SCRIPT}" \
  --title "Cadre AI — Agent Squad for Claude Code" \
  --cols 110 \
  --rows 30 \
  --overwrite \
  "${OUTPUT}"

echo ""
echo "Cast saved: ${OUTPUT}"
echo ""
echo "── Convert to GIF ───────────────────────────────────────────────────────"
echo "  agg ${OUTPUT} ${SCRIPT_DIR}/cadre-demo.gif"
echo ""
echo "── Convert to SVG ───────────────────────────────────────────────────────"
echo "  svg-term --in ${OUTPUT} --out ${SCRIPT_DIR}/cadre-demo.svg --window"
echo ""
echo "── Convert to MP4 ───────────────────────────────────────────────────────"
echo "  agg ${OUTPUT} /tmp/cadre-demo.gif"
echo "  ffmpeg -i /tmp/cadre-demo.gif ${SCRIPT_DIR}/cadre-demo.mp4"
echo ""

#!/bin/bash
set -e

# ============================================================
# Agent Forge - Installer
# ============================================================

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_INSTALL_DIR="$HOME/.agent-forge"
CLAUDE_DIR="$HOME/.claude"
BACKUP_DIR="$CLAUDE_DIR/backup-$(date +%Y%m%d-%H%M%S)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     ${BOLD}Agent Forge Installer v${VERSION}${NC}${CYAN}      ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

# ============================================================
# PRE-FLIGHT CHECKS
# ============================================================

preflight_checks() {
    echo -e "${BOLD}Pre-flight checks...${NC}"
    local all_good=true

    # Python
    if command -v python3 &>/dev/null; then
        PY_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
        print_step "Python 3 found ($PY_VERSION)"
    else
        print_error "Python 3 not found. Please install Python 3.8+"
        all_good=false
    fi

    # Git
    if command -v git &>/dev/null; then
        print_step "Git found"
    else
        print_error "Git not found. Please install git"
        all_good=false
    fi

    # Claude Code
    if [ -d "$CLAUDE_DIR" ]; then
        print_step "Claude Code directory found (~/.claude/)"
    else
        print_warn "~/.claude/ not found — will be created"
    fi

    # Node.js (optional)
    if command -v node &>/dev/null; then
        NODE_VERSION=$(node --version 2>&1)
        print_step "Node.js found ($NODE_VERSION)"
    else
        print_info "Node.js not found (optional — needed for some MCP servers)"
    fi

    # OS detection
    if [[ "$(uname -r)" == *microsoft* ]] || [[ "$(uname -r)" == *Microsoft* ]]; then
        OS_TYPE="wsl"
        print_step "Platform: WSL (Windows Subsystem for Linux)"
    elif [[ "$(uname)" == "Darwin" ]]; then
        OS_TYPE="macos"
        print_step "Platform: macOS"
    else
        OS_TYPE="linux"
        print_step "Platform: Linux"
    fi

    if [ "$all_good" = false ]; then
        echo ""
        print_error "Some requirements are missing. Please install them and try again."
        exit 1
    fi
    echo ""
}

# ============================================================
# USER SETUP
# ============================================================

user_setup() {
    echo -e "${BOLD}Setup${NC}"
    echo ""

    # User name
    read -p "Your name: " USER_NAME
    if [ -z "$USER_NAME" ]; then
        USER_NAME="$(whoami)"
        print_info "Using system username: $USER_NAME"
    fi

    # Timezone
    DETECTED_TZ=$(cat /etc/timezone 2>/dev/null || echo "UTC")
    read -p "Timezone [$DETECTED_TZ]: " TIMEZONE
    TIMEZONE="${TIMEZONE:-$DETECTED_TZ}"

    # Install directory
    read -p "Install directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

    echo ""
}

# ============================================================
# COMPONENT SELECTION
# ============================================================

select_components() {
    echo -e "${BOLD}Select components to install:${NC}"
    echo ""

    # Core (always installed)
    echo -e "  ${GREEN}[✓]${NC} Core Framework (agents, common sense, strong agent) ${CYAN}— always installed${NC}"
    echo -e "  ${GREEN}[✓]${NC} Slash Commands (commit, delegate, voice, etc.) ${CYAN}— always installed${NC}"
    echo -e "  ${GREEN}[✓]${NC} Skills (8 Claude.ai skill files) ${CYAN}— always installed${NC}"
    echo ""

    # Optional components
    INSTALL_MEMORY=true
    INSTALL_VOICE=false
    INSTALL_BROWSER=false
    INSTALL_DESKTOP=false
    INSTALL_BRIDGE=false
    INSTALL_HOOKS=true

    read -p "  Install Memory System (claude-memory MCP)? [Y/n]: " ans
    [[ "$ans" =~ ^[Nn] ]] && INSTALL_MEMORY=false

    read -p "  Install Voice/TTS (Edge TTS)? [y/N]: " ans
    [[ "$ans" =~ ^[Yy] ]] && INSTALL_VOICE=true

    if [ "$OS_TYPE" = "wsl" ]; then
        read -p "  Install Browser Automation (Edge CDP)? [y/N]: " ans
        [[ "$ans" =~ ^[Yy] ]] && INSTALL_BROWSER=true

        read -p "  Install Desktop Automation (Excel, Word, PowerPoint)? [y/N]: " ans
        [[ "$ans" =~ ^[Yy] ]] && INSTALL_DESKTOP=true

        read -p "  Install System Bridge (live state monitoring)? [y/N]: " ans
        [[ "$ans" =~ ^[Yy] ]] && INSTALL_BRIDGE=true
    fi

    read -p "  Install Safety Hooks (pre-commit guard, correction detection)? [Y/n]: " ans
    [[ "$ans" =~ ^[Nn] ]] && INSTALL_HOOKS=false

    echo ""
}

# ============================================================
# INSTALLATION
# ============================================================

do_install() {
    echo -e "${BOLD}Installing...${NC}"
    echo ""

    # Create install directory
    mkdir -p "$INSTALL_DIR"
    print_step "Created $INSTALL_DIR"

    # Backup existing config
    if [ -f "$CLAUDE_DIR/CLAUDE.md" ] || [ -f "$CLAUDE_DIR/settings.json" ]; then
        mkdir -p "$BACKUP_DIR"
        cp -r "$CLAUDE_DIR"/*.md "$BACKUP_DIR/" 2>/dev/null || true
        cp -r "$CLAUDE_DIR"/*.json "$BACKUP_DIR/" 2>/dev/null || true
        print_step "Backed up existing config to $BACKUP_DIR"
    fi

    # ── Core Framework ──
    mkdir -p "$INSTALL_DIR/framework/common-sense"
    cp "$SCRIPT_DIR/framework/strong-agent.md" "$INSTALL_DIR/framework/"
    cp "$SCRIPT_DIR/framework/agent-preamble.md" "$INSTALL_DIR/framework/"
    cp "$SCRIPT_DIR/framework/common-sense/kernel.md" "$INSTALL_DIR/framework/common-sense/"
    cp "$SCRIPT_DIR/framework/common-sense/seeds.json" "$INSTALL_DIR/framework/common-sense/"
    cp "$SCRIPT_DIR/framework/common-sense/sense.py" "$INSTALL_DIR/framework/common-sense/"
    cp "$SCRIPT_DIR/framework/common-sense/inject.py" "$INSTALL_DIR/framework/common-sense/"
    print_step "Installed core framework"

    # ── Agents ──
    mkdir -p "$CLAUDE_DIR/agents"
    cp "$SCRIPT_DIR"/agents/*.md "$CLAUDE_DIR/agents/" 2>/dev/null || true
    cp "$SCRIPT_DIR"/agents/*.yaml "$CLAUDE_DIR/agents/" 2>/dev/null || true
    print_step "Installed $(ls "$SCRIPT_DIR"/agents/ | wc -l) agent definitions"

    # ── Commands ──
    mkdir -p "$CLAUDE_DIR/commands"
    for cmd in "$SCRIPT_DIR"/commands/*.md; do
        # Replace template variables in commands
        sed "s|{{INSTALL_DIR}}|$INSTALL_DIR|g; s|{{CWD}}|\$(pwd)|g" "$cmd" > "$CLAUDE_DIR/commands/$(basename "$cmd")"
    done
    print_step "Installed $(ls "$SCRIPT_DIR"/commands/ | wc -l) slash commands"

    # ── Skills ──
    mkdir -p "$CLAUDE_DIR/skills"
    cp "$SCRIPT_DIR"/skills/*.skill "$CLAUDE_DIR/skills/" 2>/dev/null || true
    print_step "Installed $(ls "$SCRIPT_DIR"/skills/*.skill 2>/dev/null | wc -l) skill files"

    # ── CLAUDE.md ──
    sed "s|{{USER_NAME}}|$USER_NAME|g; s|{{TIMEZONE}}|$TIMEZONE|g; s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
        "$SCRIPT_DIR/templates/CLAUDE.md.template" > "$CLAUDE_DIR/CLAUDE.md"
    print_step "Generated CLAUDE.md"

    # ── Hooks ──
    if [ "$INSTALL_HOOKS" = true ]; then
        mkdir -p "$INSTALL_DIR/hooks"/{pre-tool-use,post-tool-use,user-prompt,session-start,stop}
        cp "$SCRIPT_DIR"/hooks/pre-tool-use/*.py "$INSTALL_DIR/hooks/pre-tool-use/" 2>/dev/null || true
        cp "$SCRIPT_DIR"/hooks/post-tool-use/*.sh "$INSTALL_DIR/hooks/post-tool-use/" 2>/dev/null || true
        cp "$SCRIPT_DIR"/hooks/user-prompt/*.py "$INSTALL_DIR/hooks/user-prompt/" 2>/dev/null || true
        cp "$SCRIPT_DIR"/hooks/session-start/*.sh "$INSTALL_DIR/hooks/session-start/" 2>/dev/null || true
        cp "$SCRIPT_DIR"/hooks/stop/*.py "$INSTALL_DIR/hooks/stop/" 2>/dev/null || true
        chmod +x "$INSTALL_DIR/hooks"/*/*.sh 2>/dev/null || true
        print_step "Installed hooks"
    fi

    # ── System Bridge ──
    if [ "$INSTALL_BRIDGE" = true ]; then
        mkdir -p "$INSTALL_DIR/system-bridge"
        cp "$SCRIPT_DIR"/system-bridge/*.py "$INSTALL_DIR/system-bridge/" 2>/dev/null || true
        cp "$SCRIPT_DIR"/system-bridge/*.md "$INSTALL_DIR/system-bridge/" 2>/dev/null || true
        print_step "Installed system bridge"
    fi

    # ── MCP Servers ──
    local mcp_count=0

    if [ "$INSTALL_MEMORY" = true ] && [ -d "$SCRIPT_DIR/mcp-servers/claude-memory" ]; then
        mkdir -p "$INSTALL_DIR/mcp-servers/claude-memory"
        cp -r "$SCRIPT_DIR/mcp-servers/claude-memory/"* "$INSTALL_DIR/mcp-servers/claude-memory/" 2>/dev/null || true
        if [ -f "$INSTALL_DIR/mcp-servers/claude-memory/requirements.txt" ]; then
            pip install -q -r "$INSTALL_DIR/mcp-servers/claude-memory/requirements.txt" 2>/dev/null || true
        fi
        mcp_count=$((mcp_count + 1))
    fi

    if [ "$INSTALL_VOICE" = true ] && [ -d "$SCRIPT_DIR/mcp-servers/voice-mcp" ]; then
        mkdir -p "$INSTALL_DIR/mcp-servers/voice-mcp"
        cp -r "$SCRIPT_DIR/mcp-servers/voice-mcp/"* "$INSTALL_DIR/mcp-servers/voice-mcp/" 2>/dev/null || true
        if [ -f "$INSTALL_DIR/mcp-servers/voice-mcp/requirements.txt" ]; then
            pip install -q -r "$INSTALL_DIR/mcp-servers/voice-mcp/requirements.txt" 2>/dev/null || true
        fi
        mcp_count=$((mcp_count + 1))
    fi

    if [ "$INSTALL_BROWSER" = true ] && [ -d "$SCRIPT_DIR/mcp-servers/windows-browser" ]; then
        mkdir -p "$INSTALL_DIR/mcp-servers/windows-browser"
        cp -r "$SCRIPT_DIR/mcp-servers/windows-browser/"* "$INSTALL_DIR/mcp-servers/windows-browser/" 2>/dev/null || true
        mcp_count=$((mcp_count + 1))
    fi

    if [ "$INSTALL_DESKTOP" = true ]; then
        for server in excel-mcp word-mcp powerpoint-mcp; do
            if [ -d "$SCRIPT_DIR/mcp-servers/$server" ]; then
                mkdir -p "$INSTALL_DIR/mcp-servers/$server"
                cp -r "$SCRIPT_DIR/mcp-servers/$server/"* "$INSTALL_DIR/mcp-servers/$server/" 2>/dev/null || true
                mcp_count=$((mcp_count + 1))
            fi
        done
    fi

    [ $mcp_count -gt 0 ] && print_step "Installed $mcp_count MCP server(s)"

    # ── Generate settings.json with MCP configs ──
    generate_settings

    # ── Examples ──
    mkdir -p "$INSTALL_DIR/examples"
    cp -r "$SCRIPT_DIR/examples/"* "$INSTALL_DIR/examples/" 2>/dev/null || true

    # ── Set environment variable ──
    SHELL_RC="$HOME/.bashrc"
    [ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"

    if ! grep -q "AGENT_FORGE_DIR" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# Agent Forge" >> "$SHELL_RC"
        echo "export AGENT_FORGE_DIR=\"$INSTALL_DIR\"" >> "$SHELL_RC"
        print_step "Added AGENT_FORGE_DIR to $SHELL_RC"
    fi

    echo ""
}

# ============================================================
# GENERATE SETTINGS
# ============================================================

generate_settings() {
    # Build settings.local.json with selected MCP servers
    local settings_file="$CLAUDE_DIR/settings.local.json"

    # Start building JSON
    local mcp_block=""

    if [ "$INSTALL_MEMORY" = true ]; then
        mcp_block="$mcp_block
    \"claude-memory\": {
      \"command\": \"python3\",
      \"args\": [\"$INSTALL_DIR/mcp-servers/claude-memory/src/server.py\"],
      \"disabled\": false
    }"
    fi

    if [ "$INSTALL_VOICE" = true ]; then
        [ -n "$mcp_block" ] && mcp_block="$mcp_block,"
        mcp_block="$mcp_block
    \"voice\": {
      \"command\": \"python3\",
      \"args\": [\"$INSTALL_DIR/mcp-servers/voice-mcp/server.py\"],
      \"disabled\": false
    }"
    fi

    if [ "$INSTALL_BROWSER" = true ]; then
        [ -n "$mcp_block" ] && mcp_block="$mcp_block,"
        local win_path
        win_path=$(echo "$INSTALL_DIR" | sed 's|/mnt/\([a-z]\)/|\U\1:\\|; s|/|\\|g')
        mcp_block="$mcp_block
    \"windows-browser\": {
      \"command\": \"powershell.exe\",
      \"args\": [\"-NoProfile\", \"-ExecutionPolicy\", \"Bypass\", \"-Command\", \"cd '${win_path}\\\\mcp-servers\\\\windows-browser'; python server.py\"],
      \"disabled\": false
    }"
    fi

    if [ "$INSTALL_DESKTOP" = true ]; then
        local win_path
        win_path=$(echo "$INSTALL_DIR" | sed 's|/mnt/\([a-z]\)/|\U\1:\\|; s|/|\\|g')
        for server in excel-mcp word-mcp powerpoint-mcp; do
            [ -n "$mcp_block" ] && mcp_block="$mcp_block,"
            mcp_block="$mcp_block
    \"$server\": {
      \"command\": \"powershell.exe\",
      \"args\": [\"-NoProfile\", \"-ExecutionPolicy\", \"Bypass\", \"-Command\", \"cd '${win_path}\\\\mcp-servers\\\\${server}'; python server.py\"],
      \"disabled\": false
    }"
        done
    fi

    # Only write if we have MCP servers
    if [ -n "$mcp_block" ]; then
        cat > "$settings_file" << SETTINGS_EOF
{
  "mcpServers": {$mcp_block
  }
}
SETTINGS_EOF
        print_step "Generated settings.local.json with MCP server configs"
    fi

    # Generate hooks in settings.json if not already present
    if [ "$INSTALL_HOOKS" = true ] && [ ! -f "$CLAUDE_DIR/settings.json" ]; then
        cat > "$CLAUDE_DIR/settings.json" << HOOKS_EOF
{
  "\$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(python:*)",
      "Bash(python3:*)",
      "Bash(git:*)",
      "Bash(npm:*)",
      "mcp__claude-memory__*"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $INSTALL_DIR/hooks/pre-tool-use/pre_commit_guard.py",
            "timeout": 10,
            "statusMessage": "Pre-commit guard..."
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $INSTALL_DIR/hooks/user-prompt/detect_correction.py",
            "timeout": 5,
            "statusMessage": "Checking for corrections..."
          }
        ]
      }
    ]
  }
}
HOOKS_EOF
        print_step "Generated settings.json with hook configurations"
    fi
}

# ============================================================
# POST-INSTALL SUMMARY
# ============================================================

post_install() {
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         ${BOLD}Installation Complete!${NC}${CYAN}            ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Installed to:${NC}  $INSTALL_DIR"
    echo -e "  ${BOLD}Config:${NC}        $CLAUDE_DIR/CLAUDE.md"
    echo ""
    echo -e "  ${BOLD}Components:${NC}"
    echo -e "    ${GREEN}✓${NC} Core framework + common sense engine"
    echo -e "    ${GREEN}✓${NC} 17 sub-agent definitions"
    echo -e "    ${GREEN}✓${NC} 20+ slash commands"
    echo -e "    ${GREEN}✓${NC} 8 Claude.ai skills"
    [ "$INSTALL_MEMORY" = true ] && echo -e "    ${GREEN}✓${NC} Memory system (claude-memory MCP)"
    [ "$INSTALL_VOICE" = true ] && echo -e "    ${GREEN}✓${NC} Voice/TTS (Edge TTS)"
    [ "$INSTALL_BROWSER" = true ] && echo -e "    ${GREEN}✓${NC} Browser automation (Edge CDP)"
    [ "$INSTALL_DESKTOP" = true ] && echo -e "    ${GREEN}✓${NC} Desktop automation (Excel, Word, PowerPoint)"
    [ "$INSTALL_BRIDGE" = true ] && echo -e "    ${GREEN}✓${NC} System bridge daemon"
    [ "$INSTALL_HOOKS" = true ] && echo -e "    ${GREEN}✓${NC} Safety hooks (pre-commit guard, correction detection)"
    echo ""

    if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
        echo -e "  ${YELLOW}Backup:${NC}  $BACKUP_DIR"
        echo ""
    fi

    echo -e "  ${BOLD}Next steps:${NC}"
    echo -e "    1. Restart Claude Code to activate"
    echo -e "    2. Try: ${CYAN}/prime${NC} to explore your codebase"
    echo -e "    3. Try: ${CYAN}/commit${NC} for smart git commits"
    echo -e "    4. Try: ${CYAN}/memory${NC} to store and recall knowledge"
    echo ""
    echo -e "  ${BOLD}Documentation:${NC} $SCRIPT_DIR/docs/"
    echo -e "  ${BOLD}Examples:${NC}      $INSTALL_DIR/examples/"
    echo ""
}

# ============================================================
# MAIN
# ============================================================

main() {
    print_header
    preflight_checks
    user_setup
    select_components
    do_install
    post_install
}

main "$@"

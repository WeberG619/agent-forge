# Plugin System

Cadre's plugin system lets you install custom agents beyond the built-in
set, share agents you create, and discover agents from the community
registry.

---

## Table of Contents

1. [Installing Plugins](#installing-plugins)
2. [Creating Your Own Agent](#creating-your-own-agent)
3. [Agent File Format](#agent-file-format)
4. [Publishing to the Registry](#publishing-to-the-registry)
5. [Version Management](#version-management)
6. [Plugin Locations](#plugin-locations)

---

## Installing Plugins

### From the Community Registry

Search for agents by keyword:

```bash
cadre plugin search docker
cadre plugin search database
cadre plugin search rust
```

Install by name:

```bash
cadre plugin install docker-specialist
cadre plugin install database-admin
```

### From a URL

Install directly from any raw URL (GitHub, Gist, CDN):

```bash
# GitHub repository file (blob URL is auto-converted to raw)
cadre plugin install https://github.com/you/agents/blob/main/my-agent.md

# Raw GitHub URL
cadre plugin install https://raw.githubusercontent.com/you/agents/main/my-agent.md

# GitHub Gist
cadre plugin install https://gist.githubusercontent.com/you/abc123/raw/my-agent.md
```

### From a Local File

Install an agent file you wrote or downloaded manually:

```bash
cadre plugin install ./path/to/my-agent.md
cadre plugin install ~/Downloads/specialized-agent.yaml
```

### Listing Installed Agents

```bash
cadre plugin list
```

Lists all agents in `~/.claude/agents/` and `~/.cadre-ai/plugins/`.

### Removing an Agent

```bash
cadre plugin remove docker-specialist
```

Removes the agent from `~/.claude/agents/`.

---

## Creating Your Own Agent

An agent is a single text file — either Markdown (`.md`) or YAML (`.yaml`).
Claude Code loads all files in `~/.claude/agents/` as sub-agents.

### Quick Process

1. Copy an existing agent as a starting point:
   ```bash
   cp ~/.claude/agents/python-engineer.md ~/my-agent.md
   ```

2. Edit the file to describe your agent's role and capabilities.

3. Validate and install:
   ```bash
   cadre plugin install ~/my-agent.md
   ```

4. Restart Claude Code to load the new agent.

5. Test: in Claude Code, say `use my-agent to ...`.

---

## Agent File Format

### Markdown Format (.md)

Markdown is the recommended format.  It is human-readable, easy to edit,
and works with Claude Code's sub-agent loader.

```markdown
# Agent Name

One-sentence description of what this agent does.

## Capabilities

1. **Primary skill** — Describe what it's best at
2. **Secondary skill** — Another core capability
3. **Third skill** — Another capability

## Workflow

Describe the agent's standard approach to tasks:

1. First step — e.g. "Read existing code to understand context"
2. Second step — e.g. "Propose approach before coding"
3. Third step — e.g. "Implement and verify with tests"

## Output Format

(Optional) Describe the expected output structure.

```markdown
## Analysis

[Summary of findings]

## Recommendations

1. [Action item]
2. [Action item]
```

## Rules

- Hard constraint — agent must always follow this
- Anti-pattern — never do this
- Collaboration rule — when to hand off to another agent
```

#### Required Sections

| Section | Description |
|---------|-------------|
| `# Agent Name` | Top-level H1 heading — the agent's display name |
| `## Capabilities` | Numbered list of what the agent can do |
| `## Rules` | Hard constraints that govern the agent's behavior |

#### Optional Sections

| Section | When to Use |
|---------|------------|
| `## Workflow` | Multi-step tasks with a defined process |
| `## Output Format` | When the agent should produce structured output |
| `## Conventions` | Language-specific style rules (good for code agents) |
| `## Context` | Background knowledge the agent should always have |
| `## Handoff` | Which agents this agent delegates to |

### YAML Format (.yaml)

YAML lets you specify tools, model parameters, and other structured config.

```yaml
name: agent-name
description: One-sentence description.
tools:
  - read
  - write
  - search
  - bash
system_prompt: |
  You are a specialized agent focused on X.

  ## Capabilities

  1. **Primary skill** — What it excels at
  2. **Secondary skill** — Another capability

  ## Workflow

  1. Understand the requirement.
  2. Survey existing work.
  3. Propose approach before acting.
  4. Implement and verify.

  ## Rules

  - Always read before writing.
  - Confirm destructive actions.
  - Stay within stated scope.
```

#### Required Keys

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Slug identifier — lowercase letters, numbers, hyphens |
| `description` | string | One-line plain-text description |
| `system_prompt` | string | Full system prompt (must include `## Capabilities` and `## Rules`) |

#### Optional Keys

| Key | Type | Description |
|-----|------|-------------|
| `tools` | list | Tool names the agent is allowed to use |
| `model` | string | Claude model ID (e.g. `claude-sonnet-4-5`) |
| `temperature` | float | Sampling temperature 0.0–1.0 |

#### Available Tool Names

```
read, write, search, bash, edit, glob, grep,
web_search, web_fetch, computer, task
```

---

## Publishing to the Registry

The community registry (`plugins/registry.json`) is the index that powers
`cadre plugin search`.  To add your agent:

### Step 1: Host Your Agent File

Push it to a public GitHub repo or Gist.  The URL must be a direct
download link (raw content), not an HTML page.

```
Good: https://raw.githubusercontent.com/you/agents/main/my-agent.md
Good: https://gist.githubusercontent.com/you/abc123/raw/my-agent.md
Bad:  https://github.com/you/agents/blob/main/my-agent.md  (HTML page)
```

Note: cadre automatically converts GitHub blob URLs to raw URLs when
installing via `cadre plugin install`, but the registry should store the
raw URL directly.

### Step 2: Add a Registry Entry

Fork `cadre-ai`, open `plugins/registry.json`, and add your entry to the
JSON array:

```json
{
  "name": "my-agent",
  "description": "One sentence describing what it does.",
  "author": "your-github-username",
  "url": "https://raw.githubusercontent.com/you/agents/main/my-agent.md",
  "version": "1.0.0",
  "tags": ["tag1", "tag2", "tag3"]
}
```

**Naming rules:**
- `name` must be lowercase, hyphens only, no spaces.
- `name` must match the filename stem (`my-agent.md` -> `"name": "my-agent"`).
- Names must be unique in the registry.

**Tag guidelines:**
- Use 3–7 tags.
- Use common technology names as tags: `python`, `docker`, `aws`, `sql`.
- Avoid vague tags like `agent`, `tool`, `helper`.

### Step 3: Open a Pull Request

Submit the PR to `cadre-ai`.  Maintainers will review:

- Agent file content for quality and safety
- Registry entry format correctness
- That the hosted URL is publicly accessible

---

## Version Management

### Declaring Versions

Use [Semantic Versioning](https://semver.org/) in your registry entries:

```
1.0.0   — Initial release
1.1.0   — Added capability (backward-compatible)
1.2.0   — Another feature
2.0.0   — Breaking change to behavior or interface
```

### Updating an Installed Agent

There is no automatic update mechanism.  To update:

```bash
# Remove the old version
cadre plugin remove my-agent

# Install the latest
cadre plugin install https://raw.githubusercontent.com/you/agents/main/my-agent.md
```

Or reinstall from registry (picks up the current URL from registry.json):

```bash
cadre plugin install my-agent
```

### Pinning a Version

To pin to a specific version, use a URL that points to a tagged commit:

```bash
cadre plugin install \
  https://raw.githubusercontent.com/you/agents/v1.2.0/my-agent.md
```

### Registry Version vs File Version

The `version` field in the registry is informational — it reflects the
version the registry maintainer last verified.  The actual file at the URL
may be newer.  Always check the agent file's own changelog section if
version accuracy is critical.

---

## Plugin Locations

Cadre uses two directories for agents:

| Directory | Purpose |
|-----------|---------|
| `~/.claude/agents/` | Primary — Claude Code loads agents from here at startup |
| `~/.cadre-ai/plugins/` | Secondary — cadre plugin store (for reference/backup) |

By default, `cadre plugin install` places agents in `~/.claude/agents/`
so Claude Code can immediately use them.  You do not need to restart
Claude Code if you install during a session — sub-agents are loaded on
demand.

### Viewing All Locations

```bash
cadre plugin list
```

The output shows `source: claude` (from `~/.claude/agents/`) or
`source: cadre` (from `~/.cadre-ai/plugins/`) for each agent.

---

## Programmatic API

The plugin manager is also importable as a Python library:

```python
from pathlib import Path
from cadre_ai.plugins import (
    list_installed,
    install_from_url,
    install_from_file,
    validate_agent,
    uninstall,
    search_registry,
)

# List all installed agents
for agent in list_installed():
    print(f"{agent['name']} ({agent['format']}) — {agent['source']}")

# Validate before installing
errors = validate_agent(Path("./my-agent.md"))
if not errors:
    install_from_file(Path("./my-agent.md"))
else:
    print("Validation failed:", errors)

# Search the registry
results = search_registry("docker")
for r in results:
    print(r["name"], "—", r["description"])

# Install from URL
install_from_url("https://github.com/you/agents/blob/main/my-agent.md")

# Remove
uninstall("my-agent")
```

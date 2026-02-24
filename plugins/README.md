# Cadre Plugins

Plugins are custom agents that extend cadre-ai beyond the built-in set.
Anyone can create a plugin, share it publicly, and install plugins from others
using the `cadre plugin` commands.

---

## Quick Start

```bash
# List what you have installed
cadre plugin list

# Search the community registry
cadre plugin search docker

# Install from the registry by name
cadre plugin install docker-specialist

# Install from a GitHub URL
cadre plugin install https://github.com/you/my-agents/blob/main/my-agent.md

# Install a local file you wrote
cadre plugin install ./my-agent.md

# Remove an agent
cadre plugin remove docker-specialist
```

---

## Creating Your Own Plugin

A plugin is a single `.md` or `.yaml` file that follows the cadre agent format.

### Markdown Format (.md)

The simplest format — use this for most agents.

```markdown
# My Agent Name

Short description of what this agent does.

## Capabilities

1. **Primary skill** — What it excels at
2. **Secondary skill** — Another capability
3. **Third skill** — Another capability

## Workflow

1. Step one — how the agent approaches tasks
2. Step two — what it does next
3. Step three — how it wraps up

## Rules

- Hard constraint one
- Hard constraint two
- Never do X
- Always do Y
```

**Required sections:**

| Section | Purpose |
|---------|---------|
| `# Agent Name` | Top-level heading, first line of file |
| `## Capabilities` | What the agent can do |
| `## Rules` | Hard constraints that govern behavior |

**Optional but recommended sections:** `## Workflow`, `## Output Format`,
`## Conventions`, `## Context`

### YAML Format (.yaml)

Use YAML when you need to specify tools, model, or temperature.

```yaml
name: my-agent
description: Short description of what this agent does.
tools:
  - read
  - write
  - search
  - bash
system_prompt: |
  You are a specialized agent that does X.

  ## Capabilities

  1. **Primary skill** — What it excels at
  2. **Secondary skill** — Another capability

  ## Workflow

  1. Read the task requirements.
  2. Plan the approach.
  3. Execute and verify.

  ## Rules

  - Hard constraint one
  - Never do X without confirming first
```

**Required keys:**

| Key | Purpose |
|-----|---------|
| `name` | Slug identifier (lowercase, hyphens ok) |
| `description` | One-line description shown in listings |
| `system_prompt` | The agent's full system prompt |

**Optional keys:** `tools`, `model`, `temperature`

---

## Testing Your Plugin

Before sharing, validate and test your agent locally:

```bash
# Validate the file structure
cadre plugin install ./my-agent.md

# Claude Code will load it automatically from ~/.claude/agents/
# Start a new Claude Code session and try: use my-agent to ...
```

---

## Sharing Your Plugin

### Option 1: GitHub Gist (quickest)

1. Create a public Gist at https://gist.github.com
2. Paste your agent file content
3. Click "Raw" to get the direct URL
4. Share the raw URL — others can install with:
   ```bash
   cadre plugin install https://gist.githubusercontent.com/you/abc123/raw/my-agent.md
   ```

### Option 2: GitHub Repository

1. Create a public repo (e.g. `github.com/you/cadre-agents`)
2. Add your `.md` or `.yaml` files
3. Others can install with:
   ```bash
   cadre plugin install https://github.com/you/cadre-agents/blob/main/my-agent.md
   ```

### Option 3: Submit to the Community Registry

To have your agent listed in `cadre plugin search`:

1. Fork the `cadre-ai` repo
2. Add an entry to `plugins/registry.json`:
   ```json
   {
     "name": "my-agent",
     "description": "What it does in one sentence.",
     "author": "your-github-username",
     "url": "https://raw.githubusercontent.com/you/cadre-agents/main/my-agent.md",
     "version": "1.0.0",
     "tags": ["tag1", "tag2", "tag3"]
   }
   ```
3. Open a Pull Request

Registry entries are reviewed for quality and safety before merging.

---

## Registry Format

`plugins/registry.json` is a JSON array.  Each entry:

```json
{
  "name": "agent-slug",
  "description": "One-sentence description.",
  "author": "github-username",
  "url": "https://raw.githubusercontent.com/.../agent-slug.md",
  "version": "1.0.0",
  "tags": ["tag1", "tag2"]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | Yes | Lowercase, hyphens only. Must match filename stem. |
| `description` | Yes | One sentence, plain text. |
| `author` | Yes | GitHub username or org. |
| `url` | Yes | Direct download URL (raw GitHub or CDN). |
| `version` | Yes | Semver string. |
| `tags` | Yes | 3-7 tags for search discoverability. |

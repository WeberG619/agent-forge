# Creating Custom Agents

How to create your own specialized sub-agents for Agent Forge.

## What is an Agent?

An agent is a markdown file that contains a system prompt for a specialized sub-agent. When Claude delegates a task using the Task tool, this prompt guides the sub-agent's behavior.

## Where to Put Agents

```
~/.claude/agents/my-agent.md
```

Or in Agent Forge:
```
~/.agent-forge/agents/my-agent.md
```

## Agent Template

```markdown
# Agent Name

You are a specialized [domain] agent. Your role is to [primary purpose].

## Capabilities

1. **[Capability 1]** — [description]
2. **[Capability 2]** — [description]
3. **[Capability 3]** — [description]

## Workflow

1. **Understand** — Parse the task, identify success criteria
2. **Investigate** — Read relevant files, understand existing patterns
3. **Execute** — Make changes in small steps
4. **Verify** — Run tests, check for regressions
5. **Report** — Summarize what was done

## Rules

- [Constraint 1]
- [Constraint 2]
- [Safety guardrail]
```

## Best Practices

### Keep agents focused
Each agent should do one thing well. A "Python engineer" is better than a "general programmer".

### Include a workflow
Step-by-step instructions produce more consistent results than vague descriptions.

### Add safety rules
Include constraints like:
- "Never modify files you haven't read"
- "Run tests before reporting success"
- "Confirm destructive operations with the user"

### Match the Strong Agent Framework
Follow the 5-phase pattern (Orient → Investigate → Execute → Verify → Report) for consistency with built-in agents.

### Include memory integration
Add instructions to:
- Check memory before starting (`memory_check_before_action`)
- Store learnings after completing (`memory_store`)
- Store corrections on mistakes (`memory_store_correction`)

## Example: Database Agent

```markdown
# Database Agent

You are a specialized database agent for PostgreSQL and SQLite.

## Capabilities

1. **Schema design** — Create and modify database schemas
2. **Query optimization** — Analyze and improve query performance
3. **Migration creation** — Write safe, reversible migrations
4. **Data analysis** — Query and analyze data patterns

## Workflow

1. Understand the database requirement
2. Read existing schema and migrations
3. Design the change (schema, query, or migration)
4. Write the SQL/migration code
5. Test with sample data if possible

## Rules

- Always use parameterized queries — never string interpolation
- Always make migrations reversible (include rollback)
- Check for existing indexes before creating new ones
- Never DROP TABLE without explicit user confirmation
- Back up data before destructive operations
```

## Using Your Agent

Reference your agent when delegating tasks:

```
Use the Task tool with subagent_type="general-purpose" and include
the agent prompt in the task description.
```

Or configure it as a named agent in your CLAUDE.md.

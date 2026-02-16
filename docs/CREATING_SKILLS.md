# Creating Custom Skills

Skills are structured frameworks for Claude.ai (web interface) that guide Claude through specific workflows.

## What is a Skill?

A `.skill` file is a ZIP archive containing:
- `SKILL.md` — The main skill definition and instructions
- `references/` — Supporting documents, templates, examples
- `assets/` — Images or other assets (optional)

## Creating a Skill

### 1. Create the directory structure

```
my-skill/
├── my-skill/
│   ├── SKILL.md
│   └── references/
│       ├── template.md
│       └── examples.md
```

### 2. Write the SKILL.md

```markdown
# My Skill Name

## Purpose
What this skill helps the user accomplish.

## When to Activate
Trigger phrases that should activate this skill:
- "Help me [do thing]"
- "I need to [task]"

## Framework

### Step 1: Gather Information
Ask the user:
1. [Question 1]
2. [Question 2]

### Step 2: Analysis
Based on the information:
- [Analysis step 1]
- [Analysis step 2]

### Step 3: Output
Produce:
- [Deliverable 1]
- [Deliverable 2]

## Output Format
[Template for the output]
```

### 3. Package as ZIP

```bash
cd my-skill
zip -r ../my-skill.skill my-skill/
```

### 4. Upload to Claude.ai

Go to https://claude.ai/settings → Skills → Upload

## Using Skills in Claude Code

Skills are designed for the web interface, but you can use them in Claude Code via:

```
/use-skill my-skill
```

This extracts the SKILL.md and applies the framework to your current task.

## Included Skills

| Skill | Purpose |
|-------|---------|
| idea-validator | Validate business ideas with structured analysis |
| launch-planner | Plan product launches step by step |
| product-designer | Design product features and UX |
| marketing-writer | Write marketing copy |
| product-manager | Product strategy and roadmap |
| email-drafter | Draft professional emails |
| code-review-helper | Structured code review |
| meeting-notes-processor | Process and summarize meetings |

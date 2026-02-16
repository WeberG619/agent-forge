---
description: Analyze memory patterns to find recurring issues and learnings
allowed-tools: mcp__claude-memory__memory_find_patterns, mcp__claude-memory__memory_recall, mcp__claude-memory__memory_get_corrections, mcp__voice__speak_summary
---

# Pattern Analysis

Analyze stored memories to find recurring patterns, errors, and learnings.

## Usage

```
/analyze-patterns [options]
```

**Options:**
- `errors` - Focus on recurring errors and how they were solved
- `decisions` - Analyze decision patterns across projects
- `workflows` - Identify repeated workflows
- `all` - Comprehensive pattern analysis (default)

## Analysis Steps

### Step 1: Load Pattern Data
```
mcp__claude-memory__memory_find_patterns(
    pattern_type="$ARGUMENTS or all",
    time_range_days=30
)
```

### Step 2: Load Recent Corrections
```
mcp__claude-memory__memory_get_corrections(limit=50)
```

### Step 3: Search for Error-Related Memories
```
mcp__claude-memory__memory_recall(
    query="error failed wrong incorrect problem issue",
    limit=30
)
```

### Step 4: Generate Report

Create a structured report with:

1. **Recurring Error Patterns** — What keeps going wrong, root causes, solutions
2. **Underutilized Solutions** — Corrections that exist but aren't being applied
3. **Decision Consistency** — Areas where decisions vary
4. **Workflow Opportunities** — Repeated manual steps that could be automated

### Step 5: Voice Summary

Speak a summary of key findings using voice MCP (if available).

## Report Format

```markdown
# Pattern Analysis Report
Generated: {date}

## Key Findings

### Recurring Issues (High Priority)
1. {issue}: {occurrence_count}x - Solution: {solution}

### Corrections to Compile into Rules
1. {correction_id}: {summary}

### Workflow Improvement Opportunities
1. {workflow}: Could be automated via {approach}

## Recommendations
1. {action} - Priority: {high/medium/low}
```

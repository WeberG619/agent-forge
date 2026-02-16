---
description: Claude Memory MCP - store and recall learnings, decisions, corrections
---

# Claude Memory System

You are using the Claude Memory MCP server for persistent storage.

## Core Operations

### Store Memory
```python
mcp__claude-memory__memory_store(
    content="Full content of the memory",
    project="project-name",
    tags=["tag1", "tag2"],
    importance=7,  # 1-10 scale
    memory_type="decision"  # decision, fact, preference, context, outcome, error
)
```

### Recall Memory
```python
mcp__claude-memory__memory_recall(
    query="search terms",
    project="project-name",
    limit=10
)
```

### Semantic Search
```python
mcp__claude-memory__memory_semantic_search(
    query="natural language description",
    project="project-name",
    limit=10
)
```

### Store Corrections (HIGH PRIORITY)
```python
mcp__claude-memory__memory_store_correction(
    what_claude_said="What was incorrect",
    what_was_wrong="Why it was wrong",
    correct_approach="The right way",
    project="project-name",
    category="code|architecture|workflow|preferences"
)
```

### Session Summary
```python
mcp__claude-memory__memory_summarize_session(
    project="project-name",
    summary="Brief overall summary",
    key_outcomes=["Outcome 1", "Outcome 2"],
    decisions_made=["Decision 1"],
    problems_solved=["Problem and solution"],
    open_questions=["Unresolved question"],
    next_steps=["Next action 1"]
)
```

## Session Start
```python
mcp__claude-memory__memory_smart_context(current_directory="/path/to/project")
```

## Project Management
```python
mcp__claude-memory__memory_list_projects()
mcp__claude-memory__memory_get_project(project="project-name")
mcp__claude-memory__memory_update_project(name="project-name", status="active")
```

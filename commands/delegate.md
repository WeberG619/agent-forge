# Delegate - Use Specialized Sub-Agents

## Purpose
Delegate specific tasks to specialized sub-agents

## Variables
- AGENT_TYPE: doc-scraper | test-runner | code-analyzer
- TASK: Specific task for the agent
- TARGETS: Files/URLs to process

## Usage Examples
```
/delegate doc-scraper "Scrape React documentation" https://react.dev/learn
/delegate test-runner "Run unit tests and analyze failures"
/delegate code-analyzer "Analyze src/ for performance issues"
```

## Workflow
1. Load appropriate sub-agent configuration
2. Pass focused task to sub-agent
3. Sub-agent executes with limited context
4. Results saved to designated output location
5. Summary returned to primary agent

## Benefits
- Keeps primary context clean
- Parallel execution possible
- Specialized system prompts
- Focused tool access
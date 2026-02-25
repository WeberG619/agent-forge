#!/usr/bin/env python3
"""
Agent Dispatcher - Routes Events to Agents
==========================================
Instead of just notifying, this dispatches actual agents to handle events.

Maps trigger events to specialized agent prompts and executes them
via the Claude Code CLI.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger("autonomous-agent.dispatcher")

# ============================================
# AGENT REGISTRY
# ============================================
# Define your agent types here. Each agent has a prompt template
# that gets filled with event data.

AGENT_REGISTRY = {
    # File Processing Agents
    "file-processor": {
        "description": "Process and analyze documents",
        "triggers": ["new_pdf", "new_document"],
        "prompt_template": "Analyze this file: {filepath}. Summarize its contents and identify any actionable items.",
        "timeout": 600,  # 10 minutes
        "priority": "high"
    },

    "excel-reporter": {
        "description": "Process Excel files and generate reports",
        "triggers": ["new_excel"],
        "prompt_template": "Analyze this Excel file: {filepath}. Summarize the contents and identify any actionable data.",
        "timeout": 300,
        "priority": "medium"
    },

    # Communication Agents
    "client-liaison": {
        "description": "Handle client communications",
        "triggers": ["priority_email", "client_file"],
        "prompt_template": "A {event_type} from {contact_name}: {subject}. Draft an appropriate response or action plan.",
        "timeout": 300,
        "priority": "high"
    },

    # Research Agents
    "tech-scout": {
        "description": "Research technology topics",
        "triggers": ["research_request", "tech_question"],
        "prompt_template": "Research: {topic}. Provide a summary of findings with actionable insights.",
        "timeout": 600,
        "priority": "low"
    },

    # Development Agents
    "code-architect": {
        "description": "Design system architecture",
        "triggers": ["architecture_request", "design_needed"],
        "prompt_template": "Design: {requirement}. Output a clear architecture with components and interfaces.",
        "timeout": 600,
        "priority": "medium"
    },

    "python-engineer": {
        "description": "Write Python code",
        "triggers": ["python_task", "script_request"],
        "prompt_template": "Task: {task}. Write clean, well-documented Python code.",
        "timeout": 600,
        "priority": "medium"
    }
}

# ============================================
# TRIGGER TO AGENT MAPPING
# ============================================
# Maps trigger types to which agents should handle them.

TRIGGER_AGENT_MAP = {
    # File triggers
    "new_pdf_floor_plan": ["file-processor"],
    "new_pdf_other": ["client-liaison"],
    "new_excel": ["excel-reporter"],
    "new_client_file": ["client-liaison"],

    # Email triggers
    "priority_email_critical": ["client-liaison"],
    "priority_email_high": ["client-liaison"],

    # Manual triggers (from user commands)
    "research_request": ["tech-scout"],
    "code_request": ["code-architect", "python-engineer"],
}


@dataclass
class AgentResult:
    """Result from an agent execution."""
    agent_name: str
    success: bool
    output: str
    error: Optional[str] = None
    duration_seconds: float = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class DispatchEvent:
    """An event that triggers agent dispatch."""
    trigger_type: str
    data: Dict
    priority: str = "medium"
    source: str = "automatic"


# ============================================
# AGENT DISPATCHER
# ============================================

class AgentDispatcher:
    """
    Dispatches events to appropriate agents for execution.
    """

    def __init__(self, notifier=None):
        self.notifier = notifier
        self.execution_log: list = []
        self.running_agents: Dict[str, asyncio.Task] = {}

        # Callbacks for integration
        self.on_agent_start: Optional[Callable] = None
        self.on_agent_complete: Optional[Callable] = None
        self.on_agent_error: Optional[Callable] = None

        logger.info("Agent Dispatcher initialized")

    def get_agents_for_trigger(self, trigger_type: str) -> list:
        """Get list of agents that should handle this trigger."""
        return TRIGGER_AGENT_MAP.get(trigger_type, [])

    async def dispatch(self, event: DispatchEvent) -> list:
        """
        Dispatch an event to appropriate agents.
        Returns list of AgentResult from all dispatched agents.
        """
        agents = self.get_agents_for_trigger(event.trigger_type)

        if not agents:
            logger.info(f"No agents mapped for trigger: {event.trigger_type}")
            return []

        logger.info(f"Dispatching {event.trigger_type} to agents: {agents}")

        results = []
        for agent_name in agents:
            result = await self.execute_agent(agent_name, event)
            results.append(result)

            # If first agent succeeds, might not need others
            if result.success and event.priority != "high":
                break

        return results

    async def execute_agent(self, agent_name: str, event: DispatchEvent) -> AgentResult:
        """Execute a specific agent with event data."""

        if agent_name not in AGENT_REGISTRY:
            return AgentResult(
                agent_name=agent_name,
                success=False,
                output="",
                error=f"Agent '{agent_name}' not found in registry"
            )

        agent_config = AGENT_REGISTRY[agent_name]
        timeout = agent_config.get("timeout", 300)

        # Build prompt from template
        prompt = self._build_prompt(agent_config["prompt_template"], event.data)

        logger.info(f"Executing agent: {agent_name}")
        logger.debug(f"Prompt: {prompt[:200]}...")

        # Notify start
        if self.notifier:
            await self.notifier.send(
                f"Agent Starting: {agent_name}",
                f"Processing: {event.trigger_type}\n\n{self._summarize_event(event)}",
                "low"
            )

        if self.on_agent_start:
            self.on_agent_start(agent_name, event)

        start_time = datetime.now()

        try:
            # Execute via Claude Code CLI
            output = await self._run_claude_agent(prompt, timeout)

            duration = (datetime.now() - start_time).total_seconds()

            result = AgentResult(
                agent_name=agent_name,
                success=True,
                output=output,
                duration_seconds=duration
            )

            # Log execution
            self._log_execution(result, event)

            # Notify completion
            if self.notifier:
                summary = output[:500] + "..." if len(output) > 500 else output
                await self.notifier.send(
                    f"Agent Complete: {agent_name}",
                    f"Duration: {duration:.1f}s\n\n{summary}",
                    "medium"
                )

            if self.on_agent_complete:
                self.on_agent_complete(result)

            return result

        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds()
            result = AgentResult(
                agent_name=agent_name,
                success=False,
                output="",
                error=f"Agent timed out after {timeout} seconds",
                duration_seconds=duration
            )

            if self.notifier:
                await self.notifier.send(
                    f"Agent Timeout: {agent_name}",
                    f"Agent did not complete within {timeout} seconds",
                    "high"
                )

            if self.on_agent_error:
                self.on_agent_error(result)

            return result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = str(e)

            result = AgentResult(
                agent_name=agent_name,
                success=False,
                output="",
                error=error_msg,
                duration_seconds=duration
            )

            logger.error(f"Agent {agent_name} failed: {error_msg}")

            if self.notifier:
                await self.notifier.send(
                    f"Agent Failed: {agent_name}",
                    f"Error: {error_msg}",
                    "high"
                )

            if self.on_agent_error:
                self.on_agent_error(result)

            return result

    async def _run_claude_agent(self, prompt: str, timeout: int) -> str:
        """Execute prompt via Claude Code CLI."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'claude', '-p', prompt,
                '--output-format', 'text',
                '--dangerously-skip-permissions',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )

            output = stdout.decode().strip()

            if proc.returncode != 0 and stderr:
                error = stderr.decode().strip()
                if error:
                    logger.warning(f"Claude stderr: {error}")

            return output or "Agent completed (no output)"

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            raise Exception(f"Claude execution error: {e}")

    def _build_prompt(self, template: str, data: Dict) -> str:
        """Build prompt from template and event data."""
        try:
            return template.format(**data)
        except KeyError as e:
            # If template variable missing, use placeholder
            logger.warning(f"Missing template variable: {e}")
            return template.format_map(SafeDict(data))

    def _summarize_event(self, event: DispatchEvent) -> str:
        """Create summary of event for notifications."""
        lines = [f"Trigger: {event.trigger_type}"]
        for key, value in event.data.items():
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    def _log_execution(self, result: AgentResult, event: DispatchEvent):
        """Log agent execution for tracking."""
        entry = {
            "timestamp": result.timestamp,
            "agent": result.agent_name,
            "trigger": event.trigger_type,
            "success": result.success,
            "duration": result.duration_seconds,
            "error": result.error
        }
        self.execution_log.append(entry)

        # Keep last 1000 entries
        if len(self.execution_log) > 1000:
            self.execution_log = self.execution_log[-1000:]

    def get_execution_stats(self) -> Dict:
        """Get execution statistics."""
        if not self.execution_log:
            return {"total": 0}

        total = len(self.execution_log)
        successful = sum(1 for e in self.execution_log if e["success"])

        # Group by agent
        by_agent = {}
        for entry in self.execution_log:
            agent = entry["agent"]
            if agent not in by_agent:
                by_agent[agent] = {"total": 0, "success": 0}
            by_agent[agent]["total"] += 1
            if entry["success"]:
                by_agent[agent]["success"] += 1

        return {
            "total": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_agent": by_agent
        }


class SafeDict(dict):
    """Dict that returns placeholder for missing keys."""
    def __missing__(self, key):
        return f"[{key}]"


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

async def dispatch_to_agent(trigger_type: str, data: Dict, notifier=None) -> list:
    """
    Convenience function to dispatch an event.

    Usage:
        results = await dispatch_to_agent("new_pdf_floor_plan", {"filepath": "/path/to/file.pdf"})
    """
    dispatcher = AgentDispatcher(notifier)
    event = DispatchEvent(trigger_type=trigger_type, data=data)
    return await dispatcher.dispatch(event)


async def execute_single_agent(agent_name: str, data: Dict, notifier=None) -> AgentResult:
    """
    Execute a specific agent directly.

    Usage:
        result = await execute_single_agent("file-processor", {"filepath": "/path/to/file.pdf"})
    """
    dispatcher = AgentDispatcher(notifier)
    event = DispatchEvent(trigger_type="manual", data=data)
    return await dispatcher.execute_agent(agent_name, event)


# ============================================
# TEST
# ============================================

if __name__ == "__main__":
    async def test():
        print("Testing Agent Dispatcher...")

        # Test agent lookup
        dispatcher = AgentDispatcher()
        agents = dispatcher.get_agents_for_trigger("new_pdf_floor_plan")
        print(f"Agents for new_pdf_floor_plan: {agents}")

        # Test prompt building
        template = "Process file: {filepath} from {source}"
        result = dispatcher._build_prompt(template, {"filepath": "/test.pdf", "source": "Downloads"})
        print(f"Built prompt: {result}")

        print("Agent Dispatcher test complete")

    asyncio.run(test())

"""
Dynamic Console Output - Rich console output for real-time progress reporting.

Provides:
1. RichConsoleReporter: Real-time progress display with Rich library
2. DeliverySummary: Engineering-grade final delivery summary
3. StepwiseDisplay: Step-by-step execution visualization
"""
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.tree import Tree
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .events import EventType, AgentEvent, get_event_emitter


class OutputMode(Enum):
    """Output mode for console reporter."""
    RICH = "rich"
    PLAIN = "plain"
    QUIET = "quiet"


@dataclass
class StepRecord:
    """Record of a single step execution."""
    step_number: int
    description: str
    status: str  # PENDING, IN_PROGRESS, COMPLETED, FAILED, VERIFIED
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    command: str = ""
    output: str = ""
    error: str = ""
    verification_result: str = ""

    @property
    def duration(self) -> float:
        """Get step duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


@dataclass
class TaskMetrics:
    """Metrics for task execution."""
    start_time: float = 0.0
    end_time: float = 0.0
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    lines_written: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0

    @property
    def duration(self) -> float:
        """Get total duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100


class RichConsoleReporter:
    """
    Real-time console reporter using Rich library.

    Displays:
    - [PLANNER] Thought: <analysis>
    - [EXECUTOR] Running: <command/skill>
    - [OBSERVER] Result: SUCCESS / FAILURE
    - Live metrics: Elapsed time, tokens, cost
    """

    def __init__(self, mode: OutputMode = OutputMode.RICH):
        """
        Initialize the console reporter.

        Args:
            mode: Output mode (rich, plain, quiet)
        """
        self.mode = mode if RICH_AVAILABLE else OutputMode.PLAIN
        self.console = Console() if RICH_AVAILABLE else None

        self.steps: List[StepRecord] = []
        self.metrics = TaskMetrics()
        self.current_step: Optional[StepRecord] = None
        self._live: Optional[Live] = None
        self._event_listener_id: Optional[str] = None

        # Subscribe to events
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        """Subscribe to agent events."""
        emitter = get_event_emitter()

        def on_event(event: AgentEvent):
            self._handle_event(event)

        emitter.on_all(on_event)

    def _handle_event(self, event: AgentEvent):
        """Handle an agent event."""
        if self.mode == OutputMode.QUIET:
            return

        event_type = event.event_type

        if event_type == EventType.AGENT_START:
            self._on_agent_start(event)
        elif event_type == EventType.STEP_START:
            self._on_step_start(event)
        elif event_type == EventType.PLANNER_START:
            self._on_planner_start(event)
        elif event_type == EventType.PLANNER_THINKING:
            self._on_planner_thinking(event)
        elif event_type == EventType.PLANNER_RESPONSE:
            self._on_planner_response(event)
        elif event_type == EventType.EXECUTOR_START:
            self._on_executor_start(event)
        elif event_type == EventType.EXECUTOR_COMPLETE:
            self._on_executor_complete(event)
        elif event_type == EventType.OBSERVER_RESULT:
            self._on_observer_result(event)
        elif event_type == EventType.STEP_COMPLETE:
            self._on_step_complete(event)
        elif event_type == EventType.TOKEN_USAGE:
            self._on_token_usage(event)
        elif event_type == EventType.FILE_CREATE:
            self._on_file_create(event)
        elif event_type == EventType.FILE_MODIFY:
            self._on_file_modify(event)
        elif event_type == EventType.TASK_SUMMARY:
            self._on_task_summary(event)
        elif event_type == EventType.AGENT_COMPLETE:
            self._on_agent_complete(event)
        elif event_type == EventType.AGENT_ERROR:
            self._on_agent_error(event)

    def _print(self, message: str, style: str = None):
        """Print message with optional style."""
        if self.mode == OutputMode.QUIET:
            return

        if self.mode == OutputMode.RICH and self.console:
            self.console.print(message, style=style)
        else:
            print(message)

    def _on_agent_start(self, event: AgentEvent):
        """Handle agent start event."""
        self.metrics = TaskMetrics(start_time=time.time())
        goal = event.data.get('goal', 'Unknown task')

        if self.mode == OutputMode.RICH and self.console:
            self.console.print()
            self.console.print(Panel(
                f"[bold blue]Task:[/bold blue] {goal}",
                title="[bold green]Agent Started[/bold green]",
                border_style="green"
            ))
        else:
            print(f"\n{'='*60}")
            print(f"AGENT STARTED: {goal}")
            print(f"{'='*60}")

    def _on_step_start(self, event: AgentEvent):
        """Handle step start event."""
        step_num = event.data.get('step', len(self.steps) + 1)
        self.current_step = StepRecord(
            step_number=step_num,
            description=event.message,
            status="IN_PROGRESS",
            start_time=time.time()
        )
        self.steps.append(self.current_step)
        self.metrics.total_steps = len(self.steps)

        if self.mode == OutputMode.RICH and self.console:
            self.console.print()
            self.console.rule(f"[bold cyan]Step {step_num}[/bold cyan]")
        else:
            print(f"\n--- Step {step_num} ---")

    def _on_planner_start(self, event: AgentEvent):
        """Handle planner start event."""
        model = event.data.get('model', 'planner')
        self._print(f"[PLANNER] Analyzing task... (model: {model})", "bold yellow")

    def _on_planner_thinking(self, event: AgentEvent):
        """Handle planner thinking event."""
        if self.mode == OutputMode.RICH and self.console:
            self.console.print("  [dim]Thinking...[/dim]")

    def _on_planner_response(self, event: AgentEvent):
        """Handle planner response event."""
        thought = event.data.get('thought', '')
        command = event.data.get('command', '')
        reasoning = event.data.get('reasoning', '')

        if self.current_step:
            self.current_step.command = command

        if self.mode == OutputMode.RICH and self.console:
            if thought:
                self.console.print(f"[PLANNER] [bold yellow]Thought:[/bold yellow] {thought[:100]}...")
            if reasoning:
                self.console.print(f"[PLANNER] [dim]Reasoning:[/dim] {reasoning[:80]}...")
        else:
            if thought:
                print(f"[PLANNER] Thought: {thought[:100]}...")

    def _on_executor_start(self, event: AgentEvent):
        """Handle executor start event."""
        command = event.data.get('command', '')
        skill = event.data.get('skill', '')

        if skill:
            self._print(f"[EXECUTOR] Running skill: {skill}", "bold blue")
        else:
            display_cmd = command[:60] + "..." if len(command) > 60 else command
            self._print(f"[EXECUTOR] Running: {display_cmd}", "bold blue")

    def _on_executor_complete(self, event: AgentEvent):
        """Handle executor complete event."""
        status = event.data.get('status', 'UNKNOWN')
        style = "green" if status in ("COMPLETED", "SUCCESS") else "red"
        self._print(f"[EXECUTOR] Finished: {status}", style)

    def _on_observer_result(self, event: AgentEvent):
        """Handle observer result event."""
        status = event.data.get('status', 'UNKNOWN')
        error_category = event.data.get('error_category', '')

        if status in ("SUCCESS", "COMPLETED"):
            self._print(f"[OBSERVER] Result: SUCCESS", "bold green")
        else:
            msg = f"[OBSERVER] Result: FAILED"
            if error_category:
                msg += f" ({error_category})"
            self._print(msg, "bold red")

    def _on_step_complete(self, event: AgentEvent):
        """Handle step complete event."""
        status = event.data.get('status', 'UNKNOWN')

        if self.current_step:
            self.current_step.status = status
            self.current_step.end_time = time.time()

            if status in ("SUCCESS", "COMPLETED", "VERIFIED"):
                self.metrics.completed_steps += 1
            elif status in ("FAILED", "ERROR"):
                self.metrics.failed_steps += 1

        # Show elapsed time
        elapsed = time.time() - self.metrics.start_time
        self._print(f"  [dim]Elapsed: {elapsed:.1f}s[/dim]", "dim")

    def _on_token_usage(self, event: AgentEvent):
        """Handle token usage event."""
        input_tokens = event.data.get('input_tokens', 0)
        output_tokens = event.data.get('output_tokens', 0)

        self.metrics.input_tokens += input_tokens
        self.metrics.output_tokens += output_tokens

        if self.mode == OutputMode.RICH and self.console:
            self.console.print(
                f"  [dim]Tokens: {input_tokens} in / {output_tokens} out "
                f"(total: {self.metrics.input_tokens}/{self.metrics.output_tokens})[/dim]"
            )

    def _on_file_create(self, event: AgentEvent):
        """Handle file create event."""
        filepath = event.data.get('file', '')
        if filepath and filepath not in self.metrics.files_created:
            self.metrics.files_created.append(filepath)
        self._print(f"  [FILE] Created: {filepath}", "cyan")

    def _on_file_modify(self, event: AgentEvent):
        """Handle file modify event."""
        filepath = event.data.get('file', '')
        if filepath and filepath not in self.metrics.files_modified:
            self.metrics.files_modified.append(filepath)
        self._print(f"  [FILE] Modified: {filepath}", "cyan")

    def _on_task_summary(self, event: AgentEvent):
        """Handle task summary event."""
        summary = event.data.get('summary', {})
        self.metrics.end_time = time.time()

        # Update metrics from summary
        if 'files_created' in summary:
            for f in summary['files_created']:
                if f not in self.metrics.files_created:
                    self.metrics.files_created.append(f)

    def _on_agent_complete(self, event: AgentEvent):
        """Handle agent complete event."""
        self.metrics.end_time = time.time()
        status = event.data.get('status', 'UNKNOWN')

        if self.mode == OutputMode.RICH and self.console:
            style = "green" if status == "COMPLETED" else "red"
            self.console.print()
            self.console.print(Panel(
                f"Status: [bold]{status}[/bold]",
                title=f"[bold {style}]Agent Finished[/bold {style}]",
                border_style=style
            ))
        else:
            print(f"\n{'='*60}")
            print(f"AGENT FINISHED: {status}")
            print(f"{'='*60}")

    def _on_agent_error(self, event: AgentEvent):
        """Handle agent error event."""
        error = event.data.get('error', 'Unknown error')
        self._print(f"[ERROR] {error}", "bold red")

    def get_metrics(self) -> TaskMetrics:
        """Get current task metrics."""
        return self.metrics

    def get_steps(self) -> List[StepRecord]:
        """Get all step records."""
        return self.steps

    def reset(self):
        """Reset the reporter for a new task."""
        self.steps = []
        self.metrics = TaskMetrics()
        self.current_step = None


class DeliverySummary:
    """
    Engineering-grade final delivery summary.

    Produces a comprehensive report including:
    - Step-by-step verification results
    - Files created/modified
    - Token usage and cost
    - Duration and performance metrics
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize the delivery summary generator.

        Args:
            console: Rich console for output (optional)
        """
        self.console = console or (Console() if RICH_AVAILABLE else None)

    def generate(
        self,
        goal: str,
        steps: List[StepRecord],
        metrics: TaskMetrics,
        status: str = "UNKNOWN",
        verification_results: List[tuple] = None,
        model_costs: Dict[str, Dict[str, float]] = None
    ) -> str:
        """
        Generate a final delivery summary.

        Args:
            goal: The original task goal
            steps: List of step records
            metrics: Task metrics
            verification_results: List of (step_num, passed, message) tuples
            model_costs: Dict of model name -> {cost_input, cost_output}

        Returns:
            Formatted summary string
        """
        verification_results = verification_results or []
        model_costs = model_costs or {}

        # Calculate cost
        total_cost = self._calculate_cost(metrics, model_costs)
        metrics.estimated_cost = total_cost

        if RICH_AVAILABLE and self.console:
            return self._generate_rich(goal, steps, metrics, status, verification_results)
        else:
            return self._generate_plain(goal, steps, metrics, status, verification_results)

    def _calculate_cost(self, metrics: TaskMetrics, model_costs: Dict[str, Dict[str, float]]) -> float:
        """Calculate estimated cost based on token usage."""
        # Default costs if not specified (per 1M tokens)
        default_input_cost = 0.5
        default_output_cost = 0.5

        if model_costs:
            # Use first model's costs as default
            first_model = next(iter(model_costs.values()), {})
            input_cost = first_model.get('cost_input', default_input_cost)
            output_cost = first_model.get('cost_output', default_output_cost)
        else:
            input_cost = default_input_cost
            output_cost = default_output_cost

        cost = (metrics.input_tokens / 1_000_000) * input_cost
        cost += (metrics.output_tokens / 1_000_000) * output_cost
        return cost

    def _generate_rich(
        self,
        goal: str,
        steps: List[StepRecord],
        metrics: TaskMetrics,
        status: str,
        verification_results: List[tuple]
    ) -> str:
        """Generate Rich-formatted summary."""
        output_lines = []

        # Header
        self.console.print()
        self.console.print(Panel(
            "[bold]Final Delivery Summary[/bold]",
            border_style="blue",
            box=box.DOUBLE
        ))

        # Status
        status_color = "green" if status == "COMPLETED" else "red"
        self.console.print(f"\n[bold {status_color}]Conclusion: {status}[/bold {status_color}]")

        if verification_results or steps:
            table = Table(title="Verification Results", box=box.ROUNDED)
            table.add_column("Step", style="cyan", justify="center")
            table.add_column("Status", justify="center")
            table.add_column("Description", style="white")

            if verification_results:
                for step_num, passed, message in verification_results:
                    status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                    table.add_row(str(step_num), status, message[:50])
            else:
                for step in steps:
                    if step.status in ("COMPLETED", "SUCCESS", "VERIFIED"):
                        status = "[green]PASS[/green]"
                    elif step.status == "FAILED":
                        status = "[red]FAIL[/red]"
                    else:
                        status = f"[yellow]{step.status}[/yellow]"
                    table.add_row(str(step.step_number), status, step.description[:50])

            self.console.print(table)
            
            # Unmet Requirements section
            failed_items = [v for v in verification_results if not v[1]]
            if failed_items:
                self.console.print("\n[bold red]Unmet Requirements:[/bold red]")
                for step_num, passed, message in failed_items:
                    self.console.print(f"  [red]✗[/red] [bold]Step {step_num}:[/bold] {message}")
                
                # Root Cause Analysis
                self.console.print("\n[bold yellow]Root Cause Analysis:[/bold yellow]")
                # Attempt to extract failure reasons from failed steps
                for step in steps:
                    if step.status == "FAILED" and step.error:
                         self.console.print(f"  [yellow]![/yellow] [bold]Step {step.step_number}:[/bold] {step.error}")
                if not any(step.status == "FAILED" for step in steps):
                     self.console.print("  [dim]No explicit execution errors found; failures likely due to logic or missing patterns.[/dim]")

        # Metrics Table
        metrics_table = Table(title="Task Metrics", box=box.ROUNDED)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", style="white")

        metrics_table.add_row("Total Steps", str(metrics.total_steps))
        metrics_table.add_row("Completed", f"[green]{metrics.completed_steps}[/green]")
        metrics_table.add_row("Failed", f"[red]{metrics.failed_steps}[/red]" if metrics.failed_steps > 0 else "0")
        metrics_table.add_row("Duration", f"{metrics.duration:.2f}s")
        metrics_table.add_row("Files Created", str(len(metrics.files_created)))
        metrics_table.add_row("Files Modified", str(len(metrics.files_modified)))
        metrics_table.add_row("Input Tokens", f"{metrics.input_tokens:,}")
        metrics_table.add_row("Output Tokens", f"{metrics.output_tokens:,}")
        metrics_table.add_row("Estimated Cost", f"${metrics.estimated_cost:.6f}")

        self.console.print(metrics_table)

        # Files Created
        if metrics.files_created:
            self.console.print("\n[bold]Files Created:[/bold]")
            for f in metrics.files_created:
                self.console.print(f"  [green]+[/green] {f}")

        # Files Modified
        if metrics.files_modified:
            self.console.print("\n[bold]Files Modified:[/bold]")
            for f in metrics.files_modified:
                self.console.print(f"  [yellow]~[/yellow] {f}")

        # Features Used
        self.console.print("\n[bold]Features Used:[/bold]")
        features = [
            "Task Decomposition",
            "Skill-based Execution",
            "Step Verification",
            "Dynamic Progress Reporting",
            "Completion Gate"
        ]
        for feature in features:
            self.console.print(f"  [blue]-[/blue] {feature}")

        self.console.print()

        return ""  # Rich prints directly

    def _generate_plain(
        self,
        goal: str,
        steps: List[StepRecord],
        metrics: TaskMetrics,
        status: str,
        verification_results: List[tuple]
    ) -> str:
        """Generate plain text summary."""
        lines = []
        lines.append("")
        lines.append("=" * 60)
        lines.append("Final Delivery Summary")
        lines.append("=" * 60)

        lines.append(f"\nConclusion: {status}")

        # Verification Results
        lines.append("\nVerification Results:")
        lines.append("-" * 50)
        lines.append(f"{'Step':<6} {'Status':<10} {'Description':<30}")
        lines.append("-" * 50)

        if verification_results:
            for step_num, passed, message in verification_results:
                status = "PASS" if passed else "FAIL"
                lines.append(f"{step_num:<6} {status:<10} {message[:30]}")
        else:
            for step in steps:
                status = "PASS" if step.status in ("COMPLETED", "SUCCESS", "VERIFIED") else step.status
                lines.append(f"{step.step_number:<6} {status:<10} {step.description[:30]}")

        # Metrics
        lines.append("\nTask Metrics:")
        lines.append("-" * 30)
        lines.append(f"Total Steps:    {metrics.total_steps}")
        lines.append(f"Completed:      {metrics.completed_steps}")
        lines.append(f"Failed:         {metrics.failed_steps}")
        lines.append(f"Duration:       {metrics.duration:.2f}s")
        lines.append(f"Files Created:  {len(metrics.files_created)}")
        lines.append(f"Files Modified: {len(metrics.files_modified)}")
        lines.append(f"Input Tokens:   {metrics.input_tokens:,}")
        lines.append(f"Output Tokens:  {metrics.output_tokens:,}")
        lines.append(f"Estimated Cost: ${metrics.estimated_cost:.6f}")

        # Files
        if metrics.files_created:
            lines.append("\nFiles Created:")
            for f in metrics.files_created:
                lines.append(f"  + {f}")

        if metrics.files_modified:
            lines.append("\nFiles Modified:")
            for f in metrics.files_modified:
                lines.append(f"  ~ {f}")

        lines.append("")

        return "\n".join(lines)

    def print_summary(
        self,
        goal: str,
        steps: List[StepRecord],
        metrics: TaskMetrics,
        verification_results: List[tuple] = None,
        model_costs: Dict[str, Dict[str, float]] = None
    ):
        """Print the delivery summary to console."""
        summary = self.generate(goal, steps, metrics, verification_results, model_costs)
        if summary:  # Plain text mode
            print(summary)


def format_elapsed_time(seconds: float) -> str:
    """Format elapsed time as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def create_live_status_line(metrics: TaskMetrics) -> str:
    """Create a live status line for display."""
    elapsed = format_elapsed_time(metrics.duration)
    tokens = f"{metrics.input_tokens}/{metrics.output_tokens}"
    cost = f"${metrics.estimated_cost:.4f}"

    return f"Elapsed: {elapsed} | Tokens: {tokens} | Cost: {cost}"

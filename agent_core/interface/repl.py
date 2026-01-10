"""
Interactive REPL Interface for the Debug Agent.
Provides a Claude Code-style interactive shell experience.
"""
import os
import sys
import threading
import time
import yaml
from typing import Any, Callable, Dict, List, Optional, Tuple

# Try to import rich for beautiful output
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.text import Text
    from rich.table import Table
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Try to import prompt_toolkit for input/history
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


class AgentREPL:
    """
    Interactive REPL interface for the Debug Agent.
    Supports slash commands and streaming output.
    """

    # Slash commands registry
    COMMANDS = {
        "model": "Switch to a different model",
        "cost": "Show estimated token usage/cost",
        "clear": "Clear context and memory",
        "status": "Show current session status",
        "history": "Show command history",
        "config": "Show current configuration",
        "help": "Show available commands",
        "exit": "Exit the REPL",
        "quit": "Exit the REPL",
    }

    def __init__(
        self,
        orchestrator=None,
        config: Optional[Dict[str, Any]] = None,
        config_path: str = "config.yaml",
        history_file: str = ".agent_history"
    ):
        """
        Initialize the AgentREPL.

        Args:
            orchestrator: AgentOrchestrator instance
            config: Configuration dictionary
            config_path: Path to config file for saving updates
            history_file: Path to command history file
        """
        self.orchestrator = orchestrator
        self.config = config or {}
        self.config_path = config_path
        self.history_file = history_file

        # Session tracking
        self.current_session_id: Optional[str] = None
        self.token_usage = {"input": 0, "output": 0}
        self.session_start_time: Optional[float] = None

        # Initialize console for rich output
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None

        # Initialize prompt session
        self.prompt_session = None
        if PROMPT_TOOLKIT_AVAILABLE:
            try:
                self.prompt_session = PromptSession(
                    history=FileHistory(history_file),
                    auto_suggest=AutoSuggestFromHistory(),
                )
            except Exception:
                pass

        # Command handlers
        self._command_handlers: Dict[str, Callable] = {
            "model": self._handle_model,
            "cost": self._handle_cost,
            "clear": self._handle_clear,
            "status": self._handle_status,
            "history": self._handle_history,
            "config": self._handle_config,
            "help": self._handle_help,
            "exit": self._handle_exit,
            "quit": self._handle_exit,
        }

    def parse_input(self, user_input: str) -> Tuple[str, Any]:
        """
        Parse user input to determine action type.

        Args:
            user_input: Raw user input string

        Returns:
            Tuple of (action_type, payload)
            - ("command", (cmd_name, args)) for slash commands
            - ("task", task_description) for regular tasks
        """
        user_input = user_input.strip()

        if not user_input:
            return ("empty", None)

        if user_input.startswith("/"):
            # Parse slash command
            parts = user_input[1:].split(maxsplit=1)
            cmd_name = parts[0].lower() if parts else ""
            cmd_args = parts[1] if len(parts) > 1 else ""
            return ("command", (cmd_name, cmd_args))
        else:
            # Regular task
            return ("task", user_input)

    def handle_command(self, cmd_name: str, cmd_args: str) -> bool:
        """
        Handle a slash command.

        Args:
            cmd_name: Command name (without slash)
            cmd_args: Command arguments

        Returns:
            True if should continue REPL, False to exit
        """
        handler = self._command_handlers.get(cmd_name)

        if handler:
            return handler(cmd_args)
        else:
            self._print_error(f"Unknown command: /{cmd_name}")
            self._print_info("Type /help for available commands")
            return True

    def _handle_model(self, args: str) -> bool:
        """Handle /model command."""
        if not args:
            # Show current model
            current = self.config.get("current_model", "default")
            available = list(self.config.get("models", {}).keys())
            self._print_info(f"Current model: {current}")
            self._print_info(f"Available models: {', '.join(available) if available else 'none configured'}")
            return True

        model_name = args.strip()
        models_config = self.config.get("models", {})

        # Check if model exists in config
        if model_name not in models_config:
            # Check if it's an API model that needs a key
            if self._is_api_model(model_name):
                self._print_info(f"Model '{model_name}' requires an API key.")
                api_key = self._prompt_for_api_key(model_name)
                if api_key:
                    # Add model to config
                    if "models" not in self.config:
                        self.config["models"] = {}
                    self.config["models"][model_name] = {
                        "type": "openai-compatible",
                        "api_key": api_key
                    }
                    # Save API key
                    if "api_keys" not in self.config:
                        self.config["api_keys"] = {}
                    self.config["api_keys"][model_name] = api_key
                    self._save_config()
                    self._print_success(f"API key saved for {model_name}")
                else:
                    self._print_error("No API key provided, model not switched")
                    return True

        # Switch model
        self.config["current_model"] = model_name
        self._print_success(f"Switched to model: {model_name}")

        # Update orchestrator if available
        if self.orchestrator and hasattr(self.orchestrator, 'model_manager'):
            try:
                self.orchestrator.model_manager.get_model(model_name)
            except Exception as e:
                self._print_warning(f"Could not load model: {e}")

        return True

    def _handle_cost(self, args: str) -> bool:
        """Handle /cost command."""
        # Calculate estimated cost
        input_tokens = self.token_usage.get("input", 0)
        output_tokens = self.token_usage.get("output", 0)
        total_tokens = input_tokens + output_tokens

        # Rough cost estimation (varies by model)
        # Using GPT-4 pricing as reference: $0.03/1K input, $0.06/1K output
        input_cost = (input_tokens / 1000) * 0.03
        output_cost = (output_tokens / 1000) * 0.06
        total_cost = input_cost + output_cost

        if RICH_AVAILABLE and self.console:
            table = Table(title="Session Token Usage")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Input Tokens", str(input_tokens))
            table.add_row("Output Tokens", str(output_tokens))
            table.add_row("Total Tokens", str(total_tokens))
            table.add_row("Estimated Cost", f"${total_cost:.4f}")
            self.console.print(table)
        else:
            print(f"Input Tokens: {input_tokens}")
            print(f"Output Tokens: {output_tokens}")
            print(f"Total Tokens: {total_tokens}")
            print(f"Estimated Cost: ${total_cost:.4f}")

        return True

    def _handle_clear(self, args: str) -> bool:
        """Handle /clear command."""
        # Clear memory
        if self.orchestrator and hasattr(self.orchestrator, 'memory'):
            self.orchestrator.memory.clear()

        # Reset token usage
        self.token_usage = {"input": 0, "output": 0}

        # Clear current session
        self.current_session_id = None

        self._print_success("Context and memory cleared")
        return True

    def _handle_status(self, args: str) -> bool:
        """Handle /status command."""
        if RICH_AVAILABLE and self.console:
            table = Table(title="Agent Status")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Current Session", self.current_session_id or "None")
            table.add_row("Current Model", self.config.get("current_model", "default"))

            if self.session_start_time:
                elapsed = time.time() - self.session_start_time
                table.add_row("Session Duration", f"{elapsed:.1f}s")

            if self.orchestrator:
                sessions = self.orchestrator.list_tasks()
                table.add_row("Total Sessions", str(len(sessions)))

            self.console.print(table)
        else:
            print(f"Current Session: {self.current_session_id or 'None'}")
            print(f"Current Model: {self.config.get('current_model', 'default')}")

        return True

    def _handle_history(self, args: str) -> bool:
        """Handle /history command."""
        if self.orchestrator and hasattr(self.orchestrator, 'memory'):
            context = self.orchestrator.memory.get_context_for_prompt()
            if RICH_AVAILABLE and self.console:
                self.console.print(Panel(context, title="Command History"))
            else:
                print("=== Command History ===")
                print(context)
        else:
            self._print_info("No history available")
        return True

    def _handle_config(self, args: str) -> bool:
        """Handle /config command."""
        # Show config (hide sensitive values)
        safe_config = self._sanitize_config(self.config)

        if RICH_AVAILABLE and self.console:
            import json
            self.console.print(Panel(
                json.dumps(safe_config, indent=2),
                title="Current Configuration"
            ))
        else:
            print("=== Current Configuration ===")
            print(yaml.dump(safe_config, default_flow_style=False))

        return True

    def _handle_help(self, args: str) -> bool:
        """Handle /help command."""
        if RICH_AVAILABLE and self.console:
            table = Table(title="Available Commands")
            table.add_column("Command", style="cyan")
            table.add_column("Description", style="white")

            for cmd, desc in self.COMMANDS.items():
                table.add_row(f"/{cmd}", desc)

            self.console.print(table)
            self.console.print("\n[dim]Type any text without / to run it as a task[/dim]")
        else:
            print("=== Available Commands ===")
            for cmd, desc in self.COMMANDS.items():
                print(f"  /{cmd:<10} - {desc}")
            print("\nType any text without / to run it as a task")

        return True

    def _handle_exit(self, args: str) -> bool:
        """Handle /exit command."""
        self._print_info("Goodbye!")
        return False

    def _is_api_model(self, model_name: str) -> bool:
        """Check if a model name suggests it needs an API key."""
        api_models = ["gpt-4", "gpt-3.5", "claude", "deepseek", "openai", "anthropic"]
        return any(api in model_name.lower() for api in api_models)

    def _prompt_for_api_key(self, model_name: str) -> Optional[str]:
        """Prompt user for API key."""
        try:
            api_key = input(f"Please enter API Key for {model_name}: ").strip()
            return api_key if api_key else None
        except (EOFError, KeyboardInterrupt):
            return None

    def _save_config(self):
        """Save current config to file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
        except Exception as e:
            self._print_error(f"Failed to save config: {e}")

    def _sanitize_config(self, config: Dict) -> Dict:
        """Remove sensitive values from config for display."""
        safe = {}
        for key, value in config.items():
            if key in ("api_keys", "secrets"):
                safe[key] = {k: "***" for k in value} if isinstance(value, dict) else "***"
            elif isinstance(value, dict):
                safe[key] = self._sanitize_config(value)
            else:
                safe[key] = value
        return safe

    def _print_info(self, message: str):
        """Print info message."""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"[INFO] {message}")

    def _print_success(self, message: str):
        """Print success message."""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[green]✓[/green] {message}")
        else:
            print(f"[OK] {message}")

    def _print_error(self, message: str):
        """Print error message."""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[red]✗[/red] {message}")
        else:
            print(f"[ERROR] {message}")

    def _print_warning(self, message: str):
        """Print warning message."""
        if RICH_AVAILABLE and self.console:
            self.console.print(f"[yellow]⚠[/yellow] {message}")
        else:
            print(f"[WARN] {message}")

    def run_task(self, task_description: str):
        """
        Run a task through the orchestrator.

        Args:
            task_description: The task to execute
        """
        if not self.orchestrator:
            self._print_error("No orchestrator configured")
            return

        self.session_start_time = time.time()

        # Show thinking spinner
        if RICH_AVAILABLE and self.console:
            with Live(
                Panel(Spinner("dots", text="Thinking..."), title="Agent"),
                console=self.console,
                refresh_per_second=10
            ) as live:
                # Create and start task
                self.current_session_id = self.orchestrator.create_task(task_description)

                # Update display
                live.update(Panel(
                    Spinner("dots", text=f"Executing: {task_description[:50]}..."),
                    title=f"Session: {self.current_session_id}"
                ))

                # Run in background thread
                task_thread = threading.Thread(
                    target=self.orchestrator.run_loop,
                    args=(self.current_session_id,),
                    daemon=True
                )
                task_thread.start()

                # Monitor progress
                while task_thread.is_alive():
                    status = self.orchestrator.get_session_status(self.current_session_id)
                    logs = self.orchestrator.get_session_logs(self.current_session_id)

                    # Update live display
                    display_text = f"Status: {status}\n\n"
                    if logs:
                        display_text += logs[-500:]  # Last 500 chars

                    live.update(Panel(
                        Text(display_text),
                        title=f"Session: {self.current_session_id}"
                    ))

                    time.sleep(0.2)

            # Show final result
            final_status = self.orchestrator.get_session_status(self.current_session_id)
            final_logs = self.orchestrator.get_session_logs(self.current_session_id)

            if final_status in ("COMPLETED", "EXITED"):
                self._print_success(f"Task completed: {final_status}")
            else:
                self._print_warning(f"Task ended: {final_status}")

            if final_logs:
                self.console.print(Panel(final_logs[-1000:], title="Output"))

        else:
            # Fallback without rich
            print(f"Starting task: {task_description}")
            self.current_session_id = self.orchestrator.create_task(task_description)
            self.orchestrator.run_loop(self.current_session_id)

            final_status = self.orchestrator.get_session_status(self.current_session_id)
            final_logs = self.orchestrator.get_session_logs(self.current_session_id)

            print(f"Status: {final_status}")
            if final_logs:
                print("Output:")
                print(final_logs[-1000:])

    def get_prompt(self) -> str:
        """Get the prompt string."""
        model = self.config.get("current_model", "agent")
        return f"[{model}] > "

    def run(self):
        """Run the main REPL loop."""
        # Print welcome message
        if RICH_AVAILABLE and self.console:
            self.console.print(Panel(
                "[bold]Debug Agent REPL[/bold]\n"
                "Type a task to execute, or use /help for commands.\n"
                "Press Ctrl+C to interrupt, /exit to quit.",
                title="Welcome"
            ))
        else:
            print("=== Debug Agent REPL ===")
            print("Type a task to execute, or use /help for commands.")
            print("Press Ctrl+C to interrupt, /exit to quit.")
            print()

        running = True
        while running:
            try:
                # Get input
                if self.prompt_session:
                    user_input = self.prompt_session.prompt(self.get_prompt())
                else:
                    user_input = input(self.get_prompt())

                # Parse and handle
                action, payload = self.parse_input(user_input)

                if action == "empty":
                    continue
                elif action == "command":
                    cmd_name, cmd_args = payload
                    running = self.handle_command(cmd_name, cmd_args)
                elif action == "task":
                    self.run_task(payload)

            except KeyboardInterrupt:
                print()  # New line after ^C
                self._print_info("Interrupted. Type /exit to quit.")
            except EOFError:
                running = False
            except Exception as e:
                self._print_error(f"Error: {e}")

        self._print_info("Session ended.")

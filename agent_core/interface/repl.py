"""
Interactive REPL Interface for the Debug Agent.
Provides a Claude Code-style interactive shell experience with hybrid role management.
"""
import getpass
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
    from rich.style import Style as RichStyle
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Try to import prompt_toolkit for input/history
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.styles import Style
    from prompt_toolkit.completion import WordCompleter, NestedCompleter, Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.validation import Validator, ValidationError
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


# Valid roles for hybrid mode
VALID_ROLES = ["planner", "coder"]


class AgentREPL:
    """
    Interactive REPL interface for the Debug Agent.
    Supports slash commands, hybrid role management, and streaming output.
    """

    # Slash commands registry
    COMMANDS = {
        "role": "Set model for a role: /role <planner|coder> <model_name>",
        "model": "Set both roles to same model: /model <model_name>",
        "models": "List available models",
        "roles": "Show current role assignments",
        "project": "Switch to a project: /project <path>",
        "projects": "List recent projects",
        "cost": "Show token usage and cost breakdown by model",
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
        history_file: str = ".agent_history",
        project_manager=None
    ):
        """
        Initialize the AgentREPL.

        Args:
            orchestrator: AgentOrchestrator instance
            config: Configuration dictionary
            config_path: Path to config file for saving updates
            history_file: Path to command history file
            project_manager: ProjectManager instance for project switching
        """
        self.orchestrator = orchestrator
        self.config = config or {}
        self.config_path = config_path
        self.history_file = history_file
        self.project_manager = project_manager

        # Ensure roles exist in config
        if "roles" not in self.config:
            self.config["roles"] = {"planner": "default", "coder": "default"}

        # Session tracking
        self.current_session_id: Optional[str] = None
        self.session_start_time: Optional[float] = None

        # Token usage tracking by model
        self.token_usage: Dict[str, Dict[str, int]] = {}

        # Initialize console for rich output
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None

        # Initialize prompt session with completer
        self.prompt_session = None
        self._completer = None
        if PROMPT_TOOLKIT_AVAILABLE:
            try:
                self._completer = self._create_completer()
                self.prompt_session = PromptSession(
                    history=FileHistory(history_file),
                    auto_suggest=AutoSuggestFromHistory(),
                    completer=self._completer,
                    complete_while_typing=True,
                    style=Style.from_dict({
                        'prompt': '#00aa00 bold',
                        'role': '#888888',
                    }),
                )
            except Exception:
                pass

        # Command handlers
        self._command_handlers: Dict[str, Callable] = {
            "role": self._handle_role,
            "model": self._handle_model,
            "models": self._handle_models,
            "roles": self._handle_roles,
            "project": self._handle_project,
            "projects": self._handle_projects,
            "cost": self._handle_cost,
            "clear": self._handle_clear,
            "status": self._handle_status,
            "history": self._handle_history,
            "config": self._handle_config,
            "help": self._handle_help,
            "exit": self._handle_exit,
            "quit": self._handle_exit,
        }

    def _create_completer(self) -> Optional[Completer]:
        """Create a nested completer for slash commands."""
        if not PROMPT_TOOLKIT_AVAILABLE:
            return None

        models = list(self.config.get("models", {}).keys())
        roles = VALID_ROLES

        # Build nested completion dict
        completions = {
            "/role": {role: {model: None for model in models} for role in roles},
            "/model": {model: None for model in models},
            "/models": None,
            "/roles": None,
            "/project": None,
            "/projects": None,
            "/cost": None,
            "/clear": None,
            "/status": None,
            "/history": None,
            "/config": None,
            "/help": None,
            "/exit": None,
            "/quit": None,
        }

        return NestedCompleter.from_nested_dict(completions)

    def get_completer(self) -> Optional[Completer]:
        """Get the current completer (for testing)."""
        return self._completer

    def _refresh_completer(self):
        """Refresh the completer with updated model list."""
        if PROMPT_TOOLKIT_AVAILABLE and self.prompt_session:
            self._completer = self._create_completer()
            self.prompt_session.completer = self._completer

    def _get_available_models(self) -> List[str]:
        """Get list of available model names."""
        return list(self.config.get("models", {}).keys())

    def _is_valid_model(self, model_name: str) -> bool:
        """Check if a model name is valid."""
        return model_name in self.config.get("models", {})

    def _is_valid_role(self, role_name: str) -> bool:
        """Check if a role name is valid."""
        return role_name in VALID_ROLES

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
            True if command succeeded and should continue REPL
            False if should exit or command failed validation
        """
        handler = self._command_handlers.get(cmd_name)

        if handler:
            return handler(cmd_args)
        else:
            self._print_error(f"Unknown command: /{cmd_name}")
            self._print_info("Type /help for available commands")
            return True

    def _handle_role(self, args: str) -> bool:
        """Handle /role command - set model for a specific role."""
        parts = args.strip().split()

        if len(parts) < 2:
            self._print_error("Usage: /role <planner|coder> <model_name>")
            self._print_info("Use Tab for autocompletion")
            return False

        role_name = parts[0].lower()
        model_name = parts[1]

        # Validate role
        if not self._is_valid_role(role_name):
            self._print_error(f"Unknown role '{role_name}'. Valid roles: {', '.join(VALID_ROLES)}")
            return False

        # Validate model
        if not self._is_valid_model(model_name):
            available = self._get_available_models()
            self._print_error(f"Unknown model '{model_name}'. Use Tab to see available models.")
            if available:
                self._print_info(f"Available: {', '.join(available[:5])}{'...' if len(available) > 5 else ''}")
            return False

        # Check if model needs API key
        model_config = self.config.get("models", {}).get(model_name, {})
        if self._needs_api_key(model_name, model_config):
            api_key = self._prompt_for_api_key(model_name)
            if not api_key:
                self._print_error("No API key provided, role not changed")
                return False
            # Save API key
            self.config["models"][model_name]["api_key"] = api_key
            self._save_config()
            self._print_success(f"API key saved for {model_name}")

        # Update role
        self.config["roles"][role_name] = model_name
        self._print_success(f"Role '{role_name}' now uses model: {model_name}")

        return True

    def _handle_model(self, args: str) -> bool:
        """Handle /model command - set both roles to same model (single mode)."""
        if not args.strip():
            # Show current models
            return self._handle_roles("")

        model_name = args.strip()

        # Validate model
        if not self._is_valid_model(model_name):
            available = self._get_available_models()
            self._print_error(f"Unknown model '{model_name}'. Use Tab to see available models.")
            if available:
                self._print_info(f"Available: {', '.join(available[:5])}{'...' if len(available) > 5 else ''}")
            return True

        # Check if model needs API key
        model_config = self.config.get("models", {}).get(model_name, {})
        if self._needs_api_key(model_name, model_config):
            api_key = self._prompt_for_api_key(model_name)
            if not api_key:
                self._print_error("No API key provided, model not switched")
                return True
            self.config["models"][model_name]["api_key"] = api_key
            self._save_config()
            self._print_success(f"API key saved for {model_name}")

        # Set both roles to this model
        self.config["roles"]["planner"] = model_name
        self.config["roles"]["coder"] = model_name
        self._print_success(f"Both planner and coder now use: {model_name}")

        return True

    def _handle_models(self, args: str) -> bool:
        """Handle /models command - list available models."""
        models = self.config.get("models", {})

        if not models:
            self._print_info("No models configured")
            return True

        if RICH_AVAILABLE and self.console:
            table = Table(title="Available Models")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="white")
            table.add_column("Cost ($/1M)", style="green")
            table.add_column("Description", style="dim")

            for name, conf in models.items():
                model_type = conf.get("type", "unknown")
                cost_in = conf.get("cost_input", 0)
                cost_out = conf.get("cost_output", 0)
                desc = conf.get("description", "")[:30]
                cost_str = f"${cost_in:.2f} / ${cost_out:.2f}" if cost_in or cost_out else "Free"
                table.add_row(name, model_type, cost_str, desc)

            self.console.print(table)
        else:
            print("=== Available Models ===")
            for name, conf in models.items():
                cost_in = conf.get("cost_input", 0)
                cost_out = conf.get("cost_output", 0)
                print(f"  {name}: ${cost_in:.2f}/${cost_out:.2f} per 1M tokens")

        return True

    def _handle_roles(self, args: str) -> bool:
        """Handle /roles command - show current role assignments."""
        roles = self.config.get("roles", {})

        if RICH_AVAILABLE and self.console:
            table = Table(title="Current Role Assignments")
            table.add_column("Role", style="cyan")
            table.add_column("Model", style="green")
            table.add_column("Cost ($/1M)", style="yellow")

            for role in VALID_ROLES:
                model_name = roles.get(role, "not set")
                model_conf = self.config.get("models", {}).get(model_name, {})
                cost_in = model_conf.get("cost_input", 0)
                cost_out = model_conf.get("cost_output", 0)
                cost_str = f"${cost_in:.2f} / ${cost_out:.2f}" if cost_in or cost_out else "Free"
                table.add_row(role.capitalize(), model_name, cost_str)

            self.console.print(table)
        else:
            print("=== Current Roles ===")
            for role in VALID_ROLES:
                model_name = roles.get(role, "not set")
                print(f"  {role}: {model_name}")

        return True

    def _handle_project(self, args: str) -> bool:
        """Handle /project command - switch to a different project."""
        if not args.strip():
            # Show current project
            project_info = self.config.get("project", {})
            if project_info:
                self._print_info(f"Current project: {project_info.get('name', 'unknown')}")
                self._print_info(f"Path: {project_info.get('path', 'unknown')}")
            elif self.project_manager:
                self._print_info(f"Current project: {self.project_manager.get_project_name()}")
                self._print_info(f"Path: {self.project_manager.get_current_project()}")
            else:
                self._print_info("No project loaded")
            return True

        project_path = args.strip()

        # Expand user home directory
        if project_path.startswith("~"):
            project_path = os.path.expanduser(project_path)

        # Make absolute
        project_path = os.path.abspath(project_path)

        # Check if path exists
        if not os.path.exists(project_path):
            self._print_error(f"Path does not exist: {project_path}")
            return True

        # Check if it's a directory
        if not os.path.isdir(project_path):
            self._print_error(f"Path is not a directory: {project_path}")
            return True

        if not self.project_manager:
            self._print_error("Project manager not available")
            return True

        # Load or initialize the project
        success = self.project_manager.load_or_init_project(project_path)
        if not success:
            self._print_error(f"Failed to load/init project: {project_path}")
            return True

        # Update config with new project info
        self.config["project"] = {
            "name": self.project_manager.get_project_name(),
            "path": self.project_manager.get_current_project()
        }

        # Add to recent projects
        self.project_manager.add_to_recent_projects(project_path)

        # Reload orchestrator with new project paths if available
        if self.orchestrator:
            try:
                # Update session db path
                new_db_path = self.project_manager.get_session_db_path()
                new_log_dir = self.project_manager.get_logs_dir()

                # Update orchestrator's session manager
                if hasattr(self.orchestrator, 'session_manager'):
                    from ..session import SessionManager
                    self.orchestrator.session_manager = SessionManager(new_db_path)

                # Update orchestrator's memory
                if hasattr(self.orchestrator, 'memory'):
                    new_history_path = self.project_manager.get_history_db_path()
                    from ..memory import HistoryMemory
                    self.orchestrator.memory = HistoryMemory(new_history_path)

                self._print_success(f"Switched to project: {self.project_manager.get_project_name()}")
                self._print_info(f"Session DB: {new_db_path}")
            except Exception as e:
                self._print_warning(f"Project switched but some components may not be updated: {e}")
        else:
            self._print_success(f"Switched to project: {self.project_manager.get_project_name()}")

        return True

    def _handle_projects(self, args: str) -> bool:
        """Handle /projects command - list recent projects."""
        if not self.project_manager:
            self._print_error("Project manager not available")
            return True

        recent = self.project_manager.get_recent_projects(limit=10)
        current = self.project_manager.get_current_project()

        if RICH_AVAILABLE and self.console:
            table = Table(title="Recent Projects")
            table.add_column("#", style="dim")
            table.add_column("Name", style="cyan")
            table.add_column("Path", style="white")
            table.add_column("Status", style="green")

            for i, path in enumerate(recent, 1):
                name = os.path.basename(path)
                status = "[current]" if path == current else ""
                table.add_row(str(i), name, path, status)

            if not recent:
                table.add_row("-", "No recent projects", "", "")

            self.console.print(table)
            self.console.print("\n[dim]Use /project <path> to switch projects[/dim]")
        else:
            print("=== Recent Projects ===")
            for i, path in enumerate(recent, 1):
                name = os.path.basename(path)
                status = " [current]" if path == current else ""
                print(f"  {i}. {name}: {path}{status}")

            if not recent:
                print("  No recent projects")

            print("\nUse /project <path> to switch projects")

        return True

    def _handle_cost(self, args: str) -> bool:
        """Handle /cost command - show token usage and cost breakdown by model."""
        models_config = self.config.get("models", {})

        if RICH_AVAILABLE and self.console:
            table = Table(title="Session Cost Breakdown")
            table.add_column("Model", style="cyan")
            table.add_column("Input Tokens", style="white")
            table.add_column("Output Tokens", style="white")
            table.add_column("Input Cost", style="green")
            table.add_column("Output Cost", style="green")
            table.add_column("Total", style="yellow bold")

            total_cost = 0.0

            for model_name, usage in self.token_usage.items():
                input_tokens = usage.get("input", 0)
                output_tokens = usage.get("output", 0)

                model_conf = models_config.get(model_name, {})
                cost_input_rate = model_conf.get("cost_input", 0)
                cost_output_rate = model_conf.get("cost_output", 0)

                input_cost = (input_tokens / 1_000_000) * cost_input_rate
                output_cost = (output_tokens / 1_000_000) * cost_output_rate
                model_total = input_cost + output_cost
                total_cost += model_total

                table.add_row(
                    model_name,
                    str(input_tokens),
                    str(output_tokens),
                    f"${input_cost:.6f}",
                    f"${output_cost:.6f}",
                    f"${model_total:.6f}"
                )

            # Add total row
            table.add_row("", "", "", "", "[bold]TOTAL[/bold]", f"[bold]${total_cost:.6f}[/bold]")

            self.console.print(table)

            if not self.token_usage:
                self._print_info("No token usage recorded yet")
        else:
            print("=== Session Cost Breakdown ===")
            total_cost = 0.0
            for model_name, usage in self.token_usage.items():
                input_tokens = usage.get("input", 0)
                output_tokens = usage.get("output", 0)
                model_conf = models_config.get(model_name, )
                cost_input_rate = model_conf.get("cost_input", 0)
                cost_output_rate = model_conf.get("cost_output", 0)
                input_cost = (input_tokens / 1_000_000) * cost_input_rate
                output_cost = (output_tokens / 1_000_000) * cost_output_rate
                model_total = input_cost + output_cost
                total_cost += model_total
                print(f"  {model_name}: {input_tokens} in / {output_tokens} out = ${model_total:.6f}")
            print(f"  TOTAL: ${total_cost:.6f}")

        return True

    def _handle_clear(self, args: str) -> bool:
        """Handle /clear command."""
        # Clear memory
        if self.orchestrator and hasattr(self.orchestrator, 'memory'):
            self.orchestrator.memory.clear()

        # Reset token usage
        self.token_usage = {}

        # Clear current session
        self.current_session_id = None

        self._print_success("Context and memory cleared")
        return True

    def _handle_status(self, args: str) -> bool:
        """Handle /status command."""
        roles = self.config.get("roles", {})

        if RICH_AVAILABLE and self.console:
            table = Table(title="Agent Status")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Current Session", self.current_session_id or "None")
            table.add_row("Planner Model", roles.get("planner", "not set"))
            table.add_row("Coder Model", roles.get("coder", "not set"))

            if self.session_start_time:
                elapsed = time.time() - self.session_start_time
                table.add_row("Session Duration", f"{elapsed:.1f}s")

            if self.orchestrator:
                sessions = self.orchestrator.list_tasks()
                table.add_row("Total Sessions", str(len(sessions)))

            self.console.print(table)
        else:
            print(f"Current Session: {self.current_session_id or 'None'}")
            print(f"Planner: {roles.get('planner', 'not set')}")
            print(f"Coder: {roles.get('coder', 'not set')}")

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
            self.console.print("[dim]Use Tab for autocompletion[/dim]")
        else:
            print("=== Available Commands ===")
            for cmd, desc in self.COMMANDS.items():
                print(f"  /{cmd:<10} - {desc}")
            print("\nType any text without / to run it as a task")
            print("Use Tab for autocompletion")

        return True

    def _handle_exit(self, args: str) -> bool:
        """Handle /exit command."""
        self._print_info("Goodbye!")
        return False

    def _needs_api_key(self, model_name: str, model_config: Dict) -> bool:
        """Check if a model needs an API key."""
        # Local models don't need keys
        if model_config.get("type") == "local":
            return False

        # Check if key is already set and valid
        api_key = model_config.get("api_key", "")
        if api_key and not api_key.startswith("YOUR_"):
            return False

        # API models need keys
        api_indicators = ["openai", "api", "gpt", "claude", "deepseek", "glm"]
        model_type = model_config.get("type", "").lower()
        return any(ind in model_type or ind in model_name.lower() for ind in api_indicators)

    def _prompt_for_api_key(self, model_name: str) -> Optional[str]:
        """Prompt user for API key with masked input."""
        try:
            if RICH_AVAILABLE and self.console:
                self.console.print(f"[yellow]Enter API Key for [{model_name}][/yellow]")

            # Use getpass for masked input
            api_key = getpass.getpass(f"API Key for {model_name} > ").strip()
            return api_key if api_key else None
        except (EOFError, KeyboardInterrupt):
            return None

    def _save_config(self):
        """Save current config to file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            self._print_error(f"Failed to save config: {e}")

    def _sanitize_config(self, config: Dict) -> Dict:
        """Remove sensitive values from config for display."""
        safe = {}
        for key, value in config.items():
            if key in ("api_keys", "secrets"):
                safe[key] = {k: "***" for k in value} if isinstance(value, dict) else "***"
            elif key == "api_key":
                safe[key] = "***"
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

    def add_token_usage(self, model_name: str, input_tokens: int, output_tokens: int):
        """
        Add token usage for a model.

        Args:
            model_name: Name of the model
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
        """
        if model_name not in self.token_usage:
            self.token_usage[model_name] = {"input": 0, "output": 0}

        self.token_usage[model_name]["input"] += input_tokens
        self.token_usage[model_name]["output"] += output_tokens

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
                        display_text += logs[-500:]

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
        """Get the prompt string with project and role info."""
        roles = self.config.get("roles", {})
        planner = roles.get("planner", "?")
        coder = roles.get("coder", "?")

        # Get project name
        project_name = "unknown"
        project_info = self.config.get("project", {})
        if project_info:
            project_name = project_info.get("name", "unknown")
        elif self.project_manager:
            project_name = self.project_manager.get_project_name()

        # Format: [Proj: <name>] [Planner: <model> | Coder: <model>]
        return f"[Proj: {project_name}] [Planner: {planner[:12]} | Coder: {coder[:12]}] ❯ "

    def get_bottom_toolbar(self):
        """Get the bottom toolbar text."""
        if not PROMPT_TOOLKIT_AVAILABLE:
            return None

        roles = self.config.get("roles", {})
        planner = roles.get("planner", "not set")
        coder = roles.get("coder", "not set")

        return HTML(
            f'<b>Planner:</b> <style bg="ansiblue">{planner}</style> | '
            f'<b>Coder:</b> <style bg="ansigreen">{coder}</style> | '
            f'<style fg="ansigray">/help for commands</style>'
        )

    def run(self):
        """Run the main REPL loop."""
        # Print welcome message
        if RICH_AVAILABLE and self.console:
            roles = self.config.get("roles", {})
            self.console.print(Panel(
                "[bold]Debug Agent REPL[/bold]\n\n"
                f"Planner: [cyan]{roles.get('planner', 'not set')}[/cyan]\n"
                f"Coder: [green]{roles.get('coder', 'not set')}[/green]\n\n"
                "Type a task to execute, or use /help for commands.\n"
                "Use [bold]Tab[/bold] for autocompletion. Press Ctrl+C to interrupt.",
                title="Welcome",
                border_style="blue"
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
                    user_input = self.prompt_session.prompt(
                        self.get_prompt(),
                        bottom_toolbar=self.get_bottom_toolbar
                    )
                else:
                    user_input = input(self.get_prompt())

                # Parse and handle
                action, payload = self.parse_input(user_input)

                if action == "empty":
                    continue
                elif action == "command":
                    cmd_name, cmd_args = payload
                    result = self.handle_command(cmd_name, cmd_args)
                    # Only exit on /exit or /quit
                    if cmd_name in ("exit", "quit") and not result:
                        running = False
                elif action == "task":
                    self.run_task(payload)

            except KeyboardInterrupt:
                print()
                self._print_info("Interrupted. Type /exit to quit.")
            except EOFError:
                running = False
            except Exception as e:
                self._print_error(f"Error: {e}")

        self._print_info("Session ended.")

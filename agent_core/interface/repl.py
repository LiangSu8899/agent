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
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# Try to import rich for beautiful output
try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.text import Text
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.style import Style as RichStyle
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.layout import Layout
    from rich.tree import Tree
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

# Try to import downloader utilities
try:
    from ..utils.downloader import (
        ModelDownloader,
        ModelMissingError,
        DownloadError,
        MODEL_PRESETS,
        create_model_config,
    )
    DOWNLOADER_AVAILABLE = True
except ImportError:
    DOWNLOADER_AVAILABLE = False

# Import event system
from ..events import EventEmitter, EventType, AgentEvent, get_event_emitter, reset_event_emitter


# Valid roles for hybrid mode
VALID_ROLES = ["planner", "coder"]


# Event type to icon/color mapping
EVENT_STYLES = {
    EventType.AGENT_START: ("rocket", "bold blue"),
    EventType.AGENT_COMPLETE: ("checkmark", "bold green"),
    EventType.AGENT_ERROR: ("cross_mark", "bold red"),
    EventType.STEP_START: ("play_button", "cyan"),
    EventType.STEP_COMPLETE: ("check_mark_button", "green"),
    EventType.PLANNER_START: ("brain", "magenta"),
    EventType.PLANNER_THINKING: ("thought_balloon", "magenta"),
    EventType.PLANNER_RESPONSE: ("light_bulb", "yellow"),
    EventType.EXECUTOR_START: ("gear", "blue"),
    EventType.EXECUTOR_RUNNING: ("hourglass_flowing_sand", "blue"),
    EventType.EXECUTOR_COMPLETE: ("white_check_mark", "green"),
    EventType.OBSERVER_START: ("eyes", "cyan"),
    EventType.OBSERVER_RESULT: ("magnifying_glass_tilted_left", "cyan"),
    EventType.FILE_CREATE: ("page_facing_up", "green"),
    EventType.FILE_MODIFY: ("pencil", "yellow"),
    EventType.FILE_DELETE: ("wastebasket", "red"),
    EventType.TASK_SUMMARY: ("clipboard", "bold white"),
}

# Role labels for display
ROLE_LABELS = {
    EventType.PLANNER_START: "[PLANNER]",
    EventType.PLANNER_THINKING: "[PLANNER]",
    EventType.PLANNER_RESPONSE: "[PLANNER]",
    EventType.EXECUTOR_START: "[EXECUTOR]",
    EventType.EXECUTOR_RUNNING: "[EXECUTOR]",
    EventType.EXECUTOR_COMPLETE: "[EXECUTOR]",
    EventType.OBSERVER_START: "[OBSERVER]",
    EventType.OBSERVER_RESULT: "[OBSERVER]",
    EventType.AGENT_START: "[AGENT]",
    EventType.AGENT_COMPLETE: "[AGENT]",
    EventType.AGENT_ERROR: "[AGENT]",
    EventType.FILE_CREATE: "[FILE]",
    EventType.FILE_MODIFY: "[FILE]",
    EventType.TASK_SUMMARY: "[SUMMARY]",
}


class AgentREPL:
    """
    Interactive REPL interface for the Debug Agent.
    Supports slash commands, hybrid role management, and streaming output.
    """

    # Slash commands registry
    COMMANDS = {
        "role": "Set model for a role: /role <planner|coder> <model_name>",
        "model": "Set/add model: /model <name> | /model add | /model download <name>",
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
        project_manager=None,
        debug: bool = False
    ):
        """
        Initialize the AgentREPL.

        Args:
            orchestrator: AgentOrchestrator instance
            config: Configuration dictionary
            config_path: Path to config file for saving updates
            history_file: Path to command history file
            project_manager: ProjectManager instance for project switching
            debug: Enable debug mode
        """
        self.orchestrator = orchestrator
        self.config = config or {}
        self.config_path = config_path
        self.history_file = history_file
        self.project_manager = project_manager
        self.debug = debug

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

        # Build model completions with subcommands
        model_completions = {model: None for model in models}
        model_completions["add"] = None
        model_completions["download"] = {model: None for model in models}

        # Build nested completion dict
        completions = {
            "/role": {role: {model: None for model in models} for role in roles},
            "/model": model_completions,
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

        # Update role in config
        self.config["roles"][role_name] = model_name

        # Sync with orchestrator
        if self.orchestrator:
            if role_name == "planner":
                self.orchestrator.set_planner_role(model_name)
            elif role_name == "coder":
                self.orchestrator.set_coder_role(model_name)

        # Save to project config for auto-restore
        self._save_project_config()

        self._print_success(f"Role '{role_name}' now uses model: {model_name}")

        return True

    def _save_project_config(self):
        """Save current roles to project config for auto-restore."""
        if not self.project_manager:
            return

        project_path = self.project_manager.get_current_project()
        if not project_path:
            return

        agent_dir = os.path.join(project_path, ".agent")
        if not os.path.isdir(agent_dir):
            return

        project_config_path = os.path.join(agent_dir, "config.yaml")

        try:
            # Load existing project config or create new
            project_config = {}
            if os.path.exists(project_config_path):
                with open(project_config_path, 'r') as f:
                    project_config = yaml.safe_load(f) or {}

            # Update roles
            project_config["roles"] = self.config.get("roles", {})

            # Save
            with open(project_config_path, 'w') as f:
                yaml.dump(project_config, f, default_flow_style=False)

        except Exception as e:
            if self.debug:
                print(f"[DEBUG] Failed to save project config: {e}")

    def _handle_model(self, args: str) -> bool:
        """Handle /model command - set both roles to same model or add new model."""
        args = args.strip()

        if not args:
            # Show current models
            return self._handle_roles("")

        # Check for subcommands
        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()

        if subcommand == "add":
            return self._handle_model_add()
        elif subcommand == "download":
            model_name = parts[1] if len(parts) > 1 else ""
            return self._handle_model_download(model_name)

        # Otherwise, treat as model name to switch to
        model_name = args

        # Validate model
        if not self._is_valid_model(model_name):
            available = self._get_available_models()
            self._print_error(f"Unknown model '{model_name}'. Use Tab to see available models.")
            if available:
                self._print_info(f"Available: {', '.join(available[:5])}{'...' if len(available) > 5 else ''}")
            self._print_info("Use '/model add' to add a new model")
            return True

        # Check if local model file exists
        model_config = self.config.get("models", {}).get(model_name, {})
        if model_config.get("type") == "local":
            model_path = model_config.get("path", "")
            if model_path and not os.path.exists(os.path.expanduser(model_path)):
                # Model file missing - offer to download
                return self._handle_missing_model(model_name, model_config)

        # Check if model needs API key
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
        
        # Sync with orchestrator
        if self.orchestrator:
            self.orchestrator.set_planner_role(model_name)
            self.orchestrator.set_coder_role(model_name)
            
        self._print_success(f"Both planner and coder now use: {model_name}")

        return True

    def _handle_missing_model(self, model_name: str, model_config: dict) -> bool:
        """Handle a missing local model file - offer to download."""
        model_path = model_config.get("path", "")
        hf_repo = model_config.get("hf_repo")
        hf_file = model_config.get("hf_file")
        url = model_config.get("url")

        self._print_warning(f"Model file not found: {model_path}")

        # Check if we have download info
        if not (hf_repo and hf_file) and not url:
            self._print_error("No download information available for this model")
            self._print_info("Please download the model manually or update the config")
            return True

        if not DOWNLOADER_AVAILABLE:
            self._print_error("Downloader not available. Install huggingface_hub: pip install huggingface_hub")
            return True

        # Ask user if they want to download
        try:
            if hf_repo and hf_file:
                self._print_info(f"Can download from HuggingFace: {hf_repo}/{hf_file}")
            elif url:
                self._print_info(f"Can download from: {url}")

            choice = input("Download now? [Y/n]: ").strip().lower()
            if choice in ("", "y", "yes"):
                return self._download_model(model_name, model_config)
            else:
                self._print_info("Download cancelled")
                return True
        except (EOFError, KeyboardInterrupt):
            self._print_info("\nDownload cancelled")
            return True

    def _download_model(self, model_name: str, model_config: dict) -> bool:
        """Download a model file."""
        if not DOWNLOADER_AVAILABLE:
            self._print_error("Downloader not available")
            return True

        hf_repo = model_config.get("hf_repo")
        hf_file = model_config.get("hf_file")
        url = model_config.get("url")

        try:
            downloader = ModelDownloader(console=self.console)

            if hf_repo and hf_file:
                self._print_info(f"Downloading from HuggingFace: {hf_repo}/{hf_file}")
                local_path = downloader.download_from_hf(hf_repo, hf_file)
            elif url:
                self._print_info(f"Downloading from URL: {url}")
                local_path = downloader.download_from_url(url)
            else:
                self._print_error("No download source available")
                return True

            # Update config with actual path
            self.config["models"][model_name]["path"] = local_path
            self._save_config()

            self._print_success(f"Model downloaded to: {local_path}")
            self._print_success(f"Model '{model_name}' is now ready to use")

            return True

        except DownloadError as e:
            self._print_error(f"Download failed: {e}")
            return True
        except Exception as e:
            self._print_error(f"Unexpected error: {e}")
            return True

    def _handle_model_download(self, model_name: str) -> bool:
        """Handle /model download <name> command."""
        if not model_name:
            self._print_error("Usage: /model download <model_name>")
            return True

        if not self._is_valid_model(model_name):
            self._print_error(f"Unknown model: {model_name}")
            return True

        model_config = self.config.get("models", {}).get(model_name, {})
        return self._download_model(model_name, model_config)

    def _handle_model_add(self) -> bool:
        """Handle /model add command - interactive wizard to add a new model."""
        if not DOWNLOADER_AVAILABLE:
            self._print_error("Model wizard requires downloader module")
            self._print_info("Install with: pip install huggingface_hub")
            return True

        self._print_info("=== Add New Model Wizard ===")
        self._print_info("Press Ctrl+C to cancel at any time\n")

        try:
            # Step 1: Model name
            name = input("Model name (e.g., my-qwen): ").strip()
            if not name:
                self._print_error("Model name is required")
                return True

            # Check if name already exists
            if name in self.config.get("models", {}):
                self._print_warning(f"Model '{name}' already exists. Overwrite? [y/N]: ")
                if input().strip().lower() != "y":
                    self._print_info("Cancelled")
                    return True

            # Step 2: Source type
            print("\nSource type:")
            print("  1) HuggingFace (recommended)")
            print("  2) Direct URL")
            print("  3) Local file (already downloaded)")

            source_choice = input("Choose [1/2/3]: ").strip()

            source_type = "huggingface"
            hf_repo = None
            hf_file = None
            url = None
            local_path = None

            if source_choice == "1":
                source_type = "huggingface"
                hf_repo = input("\nHuggingFace repo (e.g., TheBloke/Qwen-7B-GGUF): ").strip()
                if not hf_repo:
                    self._print_error("Repository ID is required")
                    return True

                hf_file = input("Filename (e.g., qwen-7b.Q4_K_M.gguf): ").strip()
                if not hf_file:
                    self._print_error("Filename is required")
                    return True

            elif source_choice == "2":
                source_type = "url"
                url = input("\nDirect URL: ").strip()
                if not url:
                    self._print_error("URL is required")
                    return True

            elif source_choice == "3":
                source_type = "local"
                local_path = input("\nLocal file path: ").strip()
                if not local_path:
                    self._print_error("Path is required")
                    return True
                local_path = os.path.expanduser(local_path)
                if not os.path.exists(local_path):
                    self._print_warning(f"File not found: {local_path}")

            else:
                self._print_error("Invalid choice")
                return True

            # Step 3: Preset selection
            print("\nSelect preset:")
            print("  1) Standard (8K context, GPU acceleration)")
            print("  2) Large (16K context, GPU acceleration)")
            print("  3) CPU Only (4K context, no GPU)")
            print("  4) Custom (enter manually)")

            preset_choice = input("Choose [1/2/3/4]: ").strip()

            preset = "standard"
            context_length = None
            n_gpu_layers = None

            if preset_choice == "1":
                preset = "standard"
            elif preset_choice == "2":
                preset = "large"
            elif preset_choice == "3":
                preset = "cpu_only"
            elif preset_choice == "4":
                preset = "custom"
                try:
                    ctx_input = input("Context length (default 8192): ").strip()
                    context_length = int(ctx_input) if ctx_input else 8192

                    gpu_input = input("GPU layers (-1 for all, 0 for CPU only): ").strip()
                    n_gpu_layers = int(gpu_input) if gpu_input else -1
                except ValueError:
                    self._print_error("Invalid number")
                    return True

            # Step 4: Description
            description = input("\nDescription (optional): ").strip()
            if not description:
                description = f"Local model: {name}"

            # Create model config
            model_config = create_model_config(
                name=name,
                source_type=source_type,
                hf_repo=hf_repo,
                hf_file=hf_file,
                url=url,
                local_path=local_path,
                preset=preset,
                context_length=context_length,
                n_gpu_layers=n_gpu_layers,
                description=description
            )

            # Save to config
            if "models" not in self.config:
                self.config["models"] = {}

            self.config["models"][name] = model_config
            self._save_config()

            self._print_success(f"Model '{name}' added to configuration")

            # Show summary
            if RICH_AVAILABLE and self.console:
                table = Table(title=f"Model: {name}")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")

                for key, value in model_config.items():
                    table.add_row(key, str(value))

                self.console.print(table)

            # Ask to download if applicable
            if source_type in ("huggingface", "url"):
                model_path = model_config.get("path", "")
                if not os.path.exists(os.path.expanduser(model_path)):
                    choice = input("\nDownload model now? [Y/n]: ").strip().lower()
                    if choice in ("", "y", "yes"):
                        return self._download_model(name, model_config)

            # Refresh completer
            self._refresh_completer()

            return True

        except (EOFError, KeyboardInterrupt):
            self._print_info("\nWizard cancelled")
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

        # Change working directory to the project path
        old_cwd = os.getcwd()
        try:
            os.chdir(project_path)
            self._print_info(f"Changed directory: {old_cwd} -> {project_path}")
        except OSError as e:
            self._print_warning(f"Could not change directory: {e}")

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
        """Handle /projects command - list recent projects with status."""
        if not self.project_manager:
            self._print_error("Project manager not available")
            return True

        # Ensure current project is in recent list
        current = self.project_manager.get_current_project()
        if current:
            self.project_manager.add_to_recent_projects(current)

        recent = self.project_manager.get_recent_projects(limit=10)

        # If no recent projects but we have a current one, add it
        if not recent and current:
            recent = [current]

        # Get current working directory
        cwd = os.getcwd()

        if RICH_AVAILABLE and self.console:
            # Show current working directory
            self.console.print(f"[dim]Current directory: {cwd}[/dim]\n")

            table = Table(title="Projects")
            table.add_column("#", style="dim")
            table.add_column("Name", style="cyan")
            table.add_column("Path", style="white")
            table.add_column("Status", style="green")
            table.add_column("Sessions", style="yellow")

            for i, path in enumerate(recent, 1):
                name = os.path.basename(path)
                is_current = path == current
                is_cwd = os.path.abspath(path) == os.path.abspath(cwd)

                # Status indicator
                status_parts = []
                if is_current:
                    status_parts.append("[bold green]ACTIVE[/bold green]")
                if is_cwd:
                    status_parts.append("[cyan]CWD[/cyan]")
                status = " ".join(status_parts)

                # Try to get session count for this project
                session_count = "-"
                try:
                    if self.project_manager.is_initialized(path):
                        db_path = self.project_manager.get_session_db_path(path)
                        if os.path.exists(db_path):
                            import sqlite3
                            conn = sqlite3.connect(db_path)
                            cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM sessions")
                            count = cursor.fetchone()[0]
                            conn.close()
                            session_count = str(count)
                except Exception:
                    pass

                table.add_row(str(i), name, path, status, session_count)

            if not recent:
                table.add_row("-", "No projects found", "", "", "")
                self.console.print(table)
                self.console.print("\n[dim]Use /project <path> to open or create a project[/dim]")
            else:
                self.console.print(table)
                self.console.print("\n[dim]Use /project <path> to switch projects (also changes directory)[/dim]")
                self.console.print("[dim]Use /history to view current project history[/dim]")
        else:
            print(f"Current directory: {cwd}\n")
            print("=== Projects ===")
            for i, path in enumerate(recent, 1):
                name = os.path.basename(path)
                status = " [ACTIVE]" if path == current else ""
                if os.path.abspath(path) == os.path.abspath(cwd):
                    status += " [CWD]"
                print(f"  {i}. {name}: {path}{status}")

            if not recent:
                print("  No projects found")

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

            # Project info
            if self.project_manager:
                project_name = self.project_manager.get_project_name()
                project_path = self.project_manager.get_current_project()
                table.add_row("Project", f"[bold]{project_name}[/bold]")
                table.add_row("Project Path", project_path or "Not set")

            # Current working directory
            table.add_row("Working Directory", os.getcwd())

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
            if self.project_manager:
                print(f"Project: {self.project_manager.get_project_name()}")
                print(f"Project Path: {self.project_manager.get_current_project()}")
            print(f"Working Directory: {os.getcwd()}")
            print(f"Current Session: {self.current_session_id or 'None'}")
            print(f"Planner: {roles.get('planner', 'not set')}")
            print(f"Coder: {roles.get('coder', 'not set')}")

        return True

    def _handle_history(self, args: str) -> bool:
        """
        Handle /history command with project context.

        Usage:
            /history              - Show current project's recent history
            /history <n>          - Show last n entries
            /history <project>    - Show history for specific project
        """
        # Parse arguments
        args = args.strip()
        limit = 10
        target_project = None

        if args:
            # Check if it's a number
            if args.isdigit():
                limit = int(args)
            else:
                # Assume it's a project name/path
                target_project = args

        # Get project info
        current_project = None
        project_name = "unknown"
        if self.project_manager:
            current_project = self.project_manager.get_current_project()
            project_name = self.project_manager.get_project_name()

        if RICH_AVAILABLE and self.console:
            # Show project context header
            header_text = f"Project: [cyan]{project_name}[/cyan]"
            if current_project:
                header_text += f" ([dim]{current_project}[/dim])"

            self.console.print(Panel(header_text, title="History Context", border_style="blue"))

            # Get history entries
            if self.orchestrator and hasattr(self.orchestrator, 'memory'):
                entries = self.orchestrator.memory.get_recent_entries(limit=limit)

                if entries:
                    table = Table(title=f"Recent History (last {len(entries)} entries)")
                    table.add_column("Step", style="dim", width=5)
                    table.add_column("Command", style="cyan", max_width=40)
                    table.add_column("Status", style="white", width=10)
                    table.add_column("Reasoning", style="dim", max_width=30)

                    for entry in entries:
                        step = str(entry.get("step", "-"))
                        command = entry.get("command", "")
                        if len(command) > 40:
                            command = command[:37] + "..."
                        status = entry.get("status", "UNKNOWN")

                        # Color status
                        if status == "SUCCESS":
                            status = f"[green]{status}[/green]"
                        elif status == "FAILED":
                            status = f"[red]{status}[/red]"
                        elif status == "SKIPPED":
                            status = f"[yellow]{status}[/yellow]"

                        reasoning = entry.get("reasoning", "")
                        if len(reasoning) > 30:
                            reasoning = reasoning[:27] + "..."

                        table.add_row(step, command, status, reasoning)

                    self.console.print(table)
                else:
                    self.console.print("[dim]No history entries found[/dim]")

                # Show session info if available
                if self.current_session_id:
                    self.console.print(f"\n[dim]Current session: {self.current_session_id}[/dim]")

            else:
                self.console.print("[dim]No history available[/dim]")

            # Show help
            self.console.print("\n[dim]Usage: /history [n] - Show last n entries[/dim]")

        else:
            # Fallback without rich
            print(f"=== History for {project_name} ===")

            if self.orchestrator and hasattr(self.orchestrator, 'memory'):
                entries = self.orchestrator.memory.get_recent_entries(limit=limit)

                if entries:
                    for entry in entries:
                        step = entry.get("step", "-")
                        command = entry.get("command", "")[:50]
                        status = entry.get("status", "UNKNOWN")
                        print(f"  [{step}] {status}: {command}")
                else:
                    print("  No history entries")
            else:
                print("  No history available")

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
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
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

    def _format_event_message(self, event: AgentEvent) -> str:
        """Format an event for display."""
        role_label = ROLE_LABELS.get(event.event_type, "[AGENT]")
        _, color = EVENT_STYLES.get(event.event_type, ("", "white"))

        # Format based on event type
        if event.event_type == EventType.PLANNER_RESPONSE:
            thought = event.data.get("thought", "")
            command = event.data.get("command", "")
            if thought:
                return f"{role_label} Thought: {thought[:80]}..."
            return f"{role_label} {event.message}"

        elif event.event_type == EventType.FILE_CREATE:
            return f"{role_label} Creating: {event.data.get('file', 'unknown')}"

        elif event.event_type == EventType.FILE_MODIFY:
            return f"{role_label} Modifying: {event.data.get('file', 'unknown')}"

        elif event.event_type == EventType.EXECUTOR_START:
            cmd = event.data.get("command", "")
            if len(cmd) > 60:
                cmd = cmd[:60] + "..."
            return f"{role_label} Executing: {cmd}"

        elif event.event_type == EventType.TASK_SUMMARY:
            return ""  # Handle separately

        return f"{role_label} {event.message}"

    def _print_task_summary(self, summary: dict):
        """Print a formatted task summary."""
        if not RICH_AVAILABLE or not self.console:
            print("\n=== Task Summary ===")
            print(f"Status: {summary.get('status', 'UNKNOWN')}")
            print(f"Steps: {summary.get('total_steps', 0)}")
            if summary.get('files_created'):
                print(f"Files created: {', '.join(summary['files_created'])}")
            return

        # Create summary table
        table = Table(title="Task Summary", show_header=False, box=None)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        status = summary.get("status", "UNKNOWN")
        status_style = "green" if status == "COMPLETED" else "red"

        table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
        table.add_row("Total Steps", str(summary.get("total_steps", 0)))
        table.add_row("Successful", f"[green]{summary.get('successful_steps', 0)}[/green]")

        if summary.get("failed_steps", 0) > 0:
            table.add_row("Failed", f"[red]{summary['failed_steps']}[/red]")

        if summary.get("files_created"):
            files = ", ".join(summary["files_created"][:5])
            if len(summary["files_created"]) > 5:
                files += f" (+{len(summary['files_created']) - 5} more)"
            table.add_row("Files Created", f"[green]{files}[/green]")

        if summary.get("files_modified"):
            files = ", ".join(summary["files_modified"][:5])
            table.add_row("Files Modified", f"[yellow]{files}[/yellow]")

        if summary.get("total_lines_written", 0) > 0:
            table.add_row("Lines Written", f"~{summary['total_lines_written']}")

        duration = summary.get("duration_seconds", 0)
        table.add_row("Duration", f"{duration:.1f}s")

        if summary.get("error_message"):
            table.add_row("Error", f"[bold red]{summary['error_message']}[/bold red]")
            
        # If there are unmet requirements from EngineeringAgent
        if "unmet_requirements" in summary and summary["unmet_requirements"]:
            table.add_row("Unmet Req.", f"[bold red]{', '.join(summary['unmet_requirements'][:3])}[/bold red]")
            
        if "root_cause_analysis" in summary and summary["root_cause_analysis"]:
            rca = "; ".join(summary["root_cause_analysis"][:2])
            table.add_row("Root Cause", f"[yellow]{rca}[/yellow]")
            
        if "repair_actions" in summary and summary["repair_actions"]:
            repairs = f"{len(summary['repair_actions'])} actions"
            table.add_row("Repairs", f"[bold cyan]{repairs}[/bold cyan]")

        self.console.print()
        self.console.print(Panel(table, border_style="green", title="[bold white on green] Engineering Delivery Report [/bold white on green]"))

    def run_task(self, task_description: str):
        """
        Run a task through the orchestrator with real-time progress display.

        Args:
            task_description: The task to execute
        """
        if not self.orchestrator:
            self._print_error("No orchestrator configured")
            return

        self.session_start_time = time.time()

        # Reset event emitter for fresh task
        reset_event_emitter()
        event_emitter = get_event_emitter()

        # State tracking
        event_log: List[str] = []
        current_step = 0
        current_status = "STARTING"
        current_thought = ""
        current_command = ""
        task_summary = None
        total_input_tokens = 0
        total_output_tokens = 0
        lock = threading.Lock()

        def on_event(event: AgentEvent):
            nonlocal current_step, current_status, task_summary
            nonlocal current_thought, current_command
            nonlocal total_input_tokens, total_output_tokens

            with lock:
                # Update current step
                if event.step > 0:
                    current_step = event.step

                # Track token usage
                if event.event_type == EventType.TOKEN_USAGE:
                    model = event.data.get("model", "unknown")
                    input_tokens = event.data.get("input_tokens", 0)
                    output_tokens = event.data.get("output_tokens", 0)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    self.add_token_usage(model, input_tokens, output_tokens)

                # Update status and capture details
                if event.event_type == EventType.PLANNER_THINKING:
                    current_status = "THINKING"
                elif event.event_type == EventType.PLANNER_RESPONSE:
                    current_thought = event.data.get("thought", "")[:80]
                    current_command = event.data.get("command", "")
                elif event.event_type == EventType.EXECUTOR_START:
                    current_status = "EXECUTING"
                    current_command = event.data.get("command", "")
                elif event.event_type == EventType.EXECUTOR_RUNNING:
                    current_status = "RUNNING"
                elif event.event_type == EventType.OBSERVER_RESULT:
                    current_status = "OBSERVING"
                elif event.event_type == EventType.AGENT_COMPLETE:
                    current_status = event.data.get("status", "COMPLETED")
                elif event.event_type == EventType.AGENT_ERROR:
                    current_status = "ERROR"
                elif event.event_type == EventType.TASK_SUMMARY:
                    task_summary = event.data.get("summary", {})

                # Format and add to log
                msg = self._format_event_message(event)
                if msg:
                    event_log.append(msg)
                    # Keep only last 20 events
                    if len(event_log) > 20:
                        event_log.pop(0)

        # Subscribe to all events
        event_emitter.on_all(on_event)

        if RICH_AVAILABLE and self.console:
            # Create and start task
            self.current_session_id = self.orchestrator.create_task(task_description)

            # Run in background thread
            task_thread = threading.Thread(
                target=self.orchestrator.run_loop,
                args=(self.current_session_id,),
                daemon=True
            )
            task_thread.start()

            # Get cost rates from config
            models_config = self.config.get("models", {})

            # Live display with progress
            with Live(console=self.console, refresh_per_second=4, transient=False) as live:
                while task_thread.is_alive():
                    with lock:
                        elapsed = time.time() - self.session_start_time

                        # Calculate estimated cost
                        total_cost = 0.0
                        for model_name, usage in self.token_usage.items():
                            model_conf = models_config.get(model_name, {})
                            cost_in = model_conf.get("cost_input", 0)
                            cost_out = model_conf.get("cost_output", 0)
                            total_cost += (usage["input"] / 1_000_000) * cost_in
                            total_cost += (usage["output"] / 1_000_000) * cost_out

                        # Build header
                        header = Text()
                        header.append("Task: ", style="bold")
                        task_display = task_description[:55] + "..." if len(task_description) > 55 else task_description
                        header.append(f"{task_display}\n", style="white")

                        # Status line with indicators
                        status_color = {
                            "THINKING": "magenta",
                            "EXECUTING": "blue",
                            "RUNNING": "yellow",
                            "OBSERVING": "cyan",
                            "COMPLETED": "green",
                            "ERROR": "red",
                        }.get(current_status, "white")

                        status_icon = {
                            "THINKING": "🧠",
                            "EXECUTING": "⚙️",
                            "RUNNING": "▶️",
                            "OBSERVING": "👁️",
                            "COMPLETED": "✅",
                            "ERROR": "❌",
                        }.get(current_status, "⏳")

                        header.append(f"\n{status_icon} ", style=status_color)
                        header.append(f"Step {current_step}", style="cyan bold")
                        header.append(f" | ", style="dim")
                        header.append(f"{current_status}", style=status_color)

                        # Show current thought/command
                        if current_thought and current_status == "THINKING":
                            header.append(f"\n💭 ", style="magenta")
                            header.append(f"{current_thought}...", style="dim magenta")

                        if current_command and current_status in ("EXECUTING", "RUNNING"):
                            cmd_display = current_command[:60] + "..." if len(current_command) > 60 else current_command
                            header.append(f"\n⚡ ", style="blue")
                            header.append(f"{cmd_display}", style="dim blue")

                        # Event log
                        log_text = Text()
                        log_text.append("\n─── Activity Log ───\n", style="dim")
                        for msg in event_log[-8:]:
                            if "[PLANNER]" in msg:
                                log_text.append(msg + "\n", style="magenta")
                            elif "[EXECUTOR]" in msg:
                                log_text.append(msg + "\n", style="blue")
                            elif "[OBSERVER]" in msg:
                                log_text.append(msg + "\n", style="cyan")
                            elif "[FILE]" in msg:
                                log_text.append(msg + "\n", style="green")
                            elif "[AGENT]" in msg:
                                log_text.append(msg + "\n", style="bold white")
                            else:
                                log_text.append(msg + "\n", style="white")

                        # Footer with stats
                        footer = Text()
                        footer.append("\n─────────────────────────────────────────────────\n", style="dim")
                        footer.append(f"⏱️  {elapsed:.1f}s", style="cyan")
                        footer.append(f"  |  ", style="dim")
                        footer.append(f"🪙 {total_input_tokens}/{total_output_tokens} tokens", style="yellow")
                        footer.append(f"  |  ", style="dim")
                        footer.append(f"💰 ${total_cost:.4f}", style="green")

                        # Combine into panel
                        content = Group(header, log_text, footer)
                        live.update(Panel(
                            content,
                            title=f"[bold]Session: {self.current_session_id}[/bold]",
                            subtitle=f"[dim]Press Ctrl+C to interrupt[/dim]",
                            border_style="blue"
                        ))

                    time.sleep(0.25)

            # Show final result
            final_status = self.orchestrator.get_session_status(self.current_session_id)

            self.console.print()
            if final_status in ("COMPLETED", "EXITED"):
                self._print_success(f"Task completed: {final_status}")
            else:
                self._print_warning(f"Task ended: {final_status}")

            # Show task summary if available
            if task_summary:
                self._print_task_summary(task_summary)

        else:
            # Fallback without rich - still show events
            def print_event(event: AgentEvent):
                timestamp = datetime.now().strftime("%H:%M:%S")
                msg = self._format_event_message(event)
                if msg:
                    print(f"[{timestamp}] {msg}")
                if event.event_type == EventType.TASK_SUMMARY:
                    summary = event.data.get("summary", {})
                    print("\n=== Task Summary ===")
                    print(f"Status: {summary.get('status', 'UNKNOWN')}")
                    print(f"Steps: {summary.get('total_steps', 0)}")
                    if summary.get('files_created'):
                        print(f"Files: {', '.join(summary['files_created'])}")

            event_emitter.on_all(print_event)

            print(f"Starting task: {task_description}")
            self.current_session_id = self.orchestrator.create_task(task_description)
            self.orchestrator.run_loop(self.current_session_id)

            elapsed = time.time() - self.session_start_time
            final_status = self.orchestrator.get_session_status(self.current_session_id)
            print(f"\nFinal Status: {final_status} (elapsed: {elapsed:.1f}s)")

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
        return f"[Proj: {project_name}] [Planner: {planner[:24]} | Coder: {coder[:24]}] ❯ "

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

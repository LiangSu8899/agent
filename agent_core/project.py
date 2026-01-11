"""
Project Manager for handling project-specific data and state.
Manages project initialization, state persistence, and path resolution.
"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .utils.paths import (
    get_global_config_dir,
    get_global_config_path,
    get_global_state_path,
    get_project_data_dir,
    get_project_session_db_path,
    get_project_history_db_path,
    get_project_logs_dir,
    is_project_initialized,
    ensure_global_dir_exists,
    ensure_project_dir_exists,
    get_project_name,
    PROJECT_DATA_DIR_NAME,
)


class ProjectManager:
    """
    Manages project-specific data and global state.
    Handles project initialization, state persistence, and path resolution.
    """

    def __init__(self, global_dir: Optional[str] = None):
        """
        Initialize the ProjectManager.

        Args:
            global_dir: Optional custom global directory (for testing)
        """
        self.global_dir = Path(global_dir) if global_dir else get_global_config_dir()
        self._ensure_global_dir()
        self._current_project: Optional[str] = None

    def _ensure_global_dir(self):
        """Ensure the global config directory exists."""
        self.global_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_path(self) -> Path:
        """Get the path to state.json."""
        return self.global_dir / "state.json"

    def _load_state(self) -> Dict[str, Any]:
        """Load the global state from state.json."""
        state_path = self._get_state_path()
        if state_path.exists():
            try:
                with open(state_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_state(self, state: Dict[str, Any]):
        """Save the global state to state.json."""
        state_path = self._get_state_path()
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)

    def get_last_project(self) -> Optional[str]:
        """
        Get the last opened project path.

        Returns:
            Path to the last project, or None if not set
        """
        state = self._load_state()
        return state.get("last_project")

    def set_last_project(self, project_path: str):
        """
        Save the last opened project path.

        Args:
            project_path: Path to the project
        """
        state = self._load_state()
        state["last_project"] = str(project_path)
        state["last_opened"] = datetime.now().isoformat()
        self._save_state(state)

    def init_project(self, project_path: str) -> Path:
        """
        Initialize a new project in the given directory.
        Creates the .agent folder and necessary subdirectories.

        Args:
            project_path: Path to initialize as a project

        Returns:
            Path to the project data directory
        """
        project_path = os.path.abspath(project_path)

        # Create .agent directory
        data_dir = ensure_project_dir_exists(project_path)

        # Create initial project config
        project_config = {
            "name": get_project_name(project_path),
            "created_at": datetime.now().isoformat(),
            "version": "1.0"
        }

        config_path = data_dir / "project.json"
        with open(config_path, 'w') as f:
            json.dump(project_config, f, indent=2)

        # Update last project
        self.set_last_project(project_path)
        self._current_project = project_path

        return data_dir

    def load_project(self, project_path: str) -> bool:
        """
        Load an existing project.

        Args:
            project_path: Path to the project

        Returns:
            True if project was loaded successfully
        """
        project_path = os.path.abspath(project_path)

        if not is_project_initialized(project_path):
            return False

        self.set_last_project(project_path)
        self._current_project = project_path
        return True

    def is_initialized(self, project_path: str) -> bool:
        """
        Check if a directory is initialized as a project.

        Args:
            project_path: Path to check

        Returns:
            True if .agent directory exists
        """
        return is_project_initialized(project_path)

    def get_session_db_path(self, project_path: Optional[str] = None) -> str:
        """
        Get the sessions database path for a project.

        Args:
            project_path: Path to the project (uses current if not specified)

        Returns:
            Path to sessions.db
        """
        path = project_path or self._current_project
        if not path:
            raise ValueError("No project path specified and no current project")
        return str(get_project_session_db_path(path))

    def get_history_db_path(self, project_path: Optional[str] = None) -> str:
        """
        Get the history database path for a project.

        Args:
            project_path: Path to the project (uses current if not specified)

        Returns:
            Path to history.db
        """
        path = project_path or self._current_project
        if not path:
            raise ValueError("No project path specified and no current project")
        return str(get_project_history_db_path(path))

    def get_logs_dir(self, project_path: Optional[str] = None) -> str:
        """
        Get the logs directory path for a project.

        Args:
            project_path: Path to the project (uses current if not specified)

        Returns:
            Path to logs directory
        """
        path = project_path or self._current_project
        if not path:
            raise ValueError("No project path specified and no current project")
        return str(get_project_logs_dir(path))

    def get_project_name(self, project_path: Optional[str] = None) -> str:
        """
        Get the project name (folder name).

        Args:
            project_path: Path to the project (uses current if not specified)

        Returns:
            Project name
        """
        path = project_path or self._current_project
        if not path:
            return "unknown"
        return get_project_name(path)

    def get_current_project(self) -> Optional[str]:
        """Get the current project path."""
        return self._current_project

    def set_current_project(self, project_path: str):
        """Set the current project path."""
        self._current_project = os.path.abspath(project_path)

    def get_global_config_path(self) -> str:
        """Get the path to the global config.yaml."""
        return str(self.global_dir / "config.yaml")

    def get_recent_projects(self, limit: int = 10) -> list:
        """
        Get a list of recent projects.

        Args:
            limit: Maximum number of projects to return

        Returns:
            List of project paths
        """
        state = self._load_state()
        recent = state.get("recent_projects", [])
        return recent[:limit]

    def add_to_recent_projects(self, project_path: str):
        """
        Add a project to the recent projects list.

        Args:
            project_path: Path to add
        """
        state = self._load_state()
        recent = state.get("recent_projects", [])

        # Remove if already exists
        project_path = os.path.abspath(project_path)
        if project_path in recent:
            recent.remove(project_path)

        # Add to front
        recent.insert(0, project_path)

        # Keep only last 20
        state["recent_projects"] = recent[:20]
        self._save_state(state)

    def resolve_startup_project(self, current_dir: str) -> Dict[str, Any]:
        """
        Resolve which project to use at startup.

        Args:
            current_dir: Current working directory

        Returns:
            Dict with 'action' and relevant data:
            - {"action": "load", "path": "..."} - Load existing project
            - {"action": "init", "path": "..."} - Initialize new project
            - {"action": "ask", "current": "...", "last": "..."} - Ask user
        """
        current_dir = os.path.abspath(current_dir)

        # Check if current directory is a project
        if self.is_initialized(current_dir):
            return {"action": "load", "path": current_dir}

        # Check for last project
        last_project = self.get_last_project()
        if last_project and self.is_initialized(last_project):
            return {
                "action": "ask",
                "current": current_dir,
                "last": last_project
            }

        # No project found anywhere
        return {"action": "init", "path": current_dir}

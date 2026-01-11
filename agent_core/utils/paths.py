"""
Path utilities for global and project-specific paths.
Defines standard locations for config, state, and project data.
"""
import os
from pathlib import Path
from typing import Optional


# Global configuration directory (user-level)
DEFAULT_GLOBAL_DIR_NAME = ".agent_os"

# Project data directory (project-level)
PROJECT_DATA_DIR_NAME = ".agent"


def get_home_dir() -> Path:
    """Get the user's home directory."""
    return Path.home()


def get_global_config_dir(custom_dir: Optional[str] = None) -> Path:
    """
    Get the global configuration directory.

    Args:
        custom_dir: Optional custom directory (for testing)

    Returns:
        Path to global config directory (~/.agent_os)
    """
    if custom_dir:
        return Path(custom_dir)
    return get_home_dir() / DEFAULT_GLOBAL_DIR_NAME


def get_global_config_path(custom_dir: Optional[str] = None) -> Path:
    """
    Get the path to the global config.yaml file.

    Args:
        custom_dir: Optional custom directory (for testing)

    Returns:
        Path to config.yaml
    """
    return get_global_config_dir(custom_dir) / "config.yaml"


def get_global_state_path(custom_dir: Optional[str] = None) -> Path:
    """
    Get the path to the global state.json file.

    Args:
        custom_dir: Optional custom directory (for testing)

    Returns:
        Path to state.json
    """
    return get_global_config_dir(custom_dir) / "state.json"


def get_project_data_dir(project_path: str) -> Path:
    """
    Get the project data directory (.agent folder).

    Args:
        project_path: Path to the project root

    Returns:
        Path to project data directory
    """
    return Path(project_path) / PROJECT_DATA_DIR_NAME


def get_project_session_db_path(project_path: str) -> Path:
    """
    Get the path to the project's sessions database.

    Args:
        project_path: Path to the project root

    Returns:
        Path to sessions.db
    """
    return get_project_data_dir(project_path) / "sessions.db"


def get_project_history_db_path(project_path: str) -> Path:
    """
    Get the path to the project's history database.

    Args:
        project_path: Path to the project root

    Returns:
        Path to history.db
    """
    return get_project_data_dir(project_path) / "history.db"


def get_project_logs_dir(project_path: str) -> Path:
    """
    Get the path to the project's logs directory.

    Args:
        project_path: Path to the project root

    Returns:
        Path to logs directory
    """
    return get_project_data_dir(project_path) / "logs"


def is_project_initialized(project_path: str) -> bool:
    """
    Check if a directory has been initialized as a project.

    Args:
        project_path: Path to check

    Returns:
        True if .agent directory exists
    """
    return get_project_data_dir(project_path).is_dir()


def ensure_global_dir_exists(custom_dir: Optional[str] = None) -> Path:
    """
    Ensure the global config directory exists.

    Args:
        custom_dir: Optional custom directory (for testing)

    Returns:
        Path to the global config directory
    """
    global_dir = get_global_config_dir(custom_dir)
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir


def ensure_project_dir_exists(project_path: str) -> Path:
    """
    Ensure the project data directory exists.

    Args:
        project_path: Path to the project root

    Returns:
        Path to the project data directory
    """
    data_dir = get_project_data_dir(project_path)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Also create logs subdirectory
    logs_dir = get_project_logs_dir(project_path)
    logs_dir.mkdir(parents=True, exist_ok=True)

    return data_dir


def get_project_name(project_path: str) -> str:
    """
    Get the project name (folder name).

    Args:
        project_path: Path to the project root

    Returns:
        Project name
    """
    return Path(project_path).name

"""
Dynamic path resolution for Ignition Toolkit.

Solves ISSUE-001: Server fails to start from different directories due to hardcoded paths.

This module provides reliable path resolution that works regardless of:
- Current working directory
- Where the server is started from
- Installation method (pip install -e . vs direct run)
- Running as frozen PyInstaller executable

All paths are calculated dynamically from the installed package location.
For frozen executables, writable paths use the IGNITION_TOOLKIT_DATA env var
to avoid writing to protected directories like Program Files.
"""

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """
    Check if running as a frozen PyInstaller executable.

    Returns:
        bool: True if running as frozen executable, False otherwise
    """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

# === Core Project Structure ===


def get_package_root() -> Path:
    """
    Get the root directory of the ignition_toolkit package.

    This is the directory containing the ignition_toolkit/ folder,
    calculated dynamically from this file's location.

    Returns:
        Path: Absolute path to package root (e.g., /git/ignition-toolbox)

    Example:
        >>> root = get_package_root()
        >>> print(root)
        /git/ignition-toolbox
    """
    # This file is at: ignition_toolkit/core/paths.py
    # Package root is 2 levels up
    return Path(__file__).parent.parent.parent.resolve()


def get_package_dir() -> Path:
    """
    Get the ignition_toolkit package directory.

    Returns:
        Path: Absolute path to ignition_toolkit/ directory

    Example:
        >>> pkg = get_package_dir()
        >>> print(pkg)
        /git/ignition-toolbox/ignition_toolkit
    """
    # This file is at: ignition_toolkit/core/paths.py
    # Package dir is 2 levels up
    return Path(__file__).parent.parent.resolve()


# === Playbook Paths ===


def get_playbooks_dir() -> Path:
    """
    Get the playbooks directory (DEPRECATED - use get_builtin_playbooks_dir instead).

    Returns:
        Path: Absolute path to playbooks/ directory

    Example:
        >>> playbooks = get_playbooks_dir()
        >>> print(playbooks)
        /git/ignition-toolbox/playbooks
    """
    return get_package_root() / "playbooks"


def get_builtin_playbooks_dir() -> Path:
    """
    Get the built-in playbooks directory.

    These are the playbooks bundled with the toolkit installation (read-only).
    Contains all built-in playbooks (Gateway, Perspective, Designer).

    Returns:
        Path: Absolute path to playbooks/ directory at project root

    Example:
        >>> builtin = get_builtin_playbooks_dir()
        >>> print(builtin)
        /git/ignition-toolbox/playbooks
    """
    # Built-in playbooks are at project root /playbooks directory
    return get_package_root() / "playbooks"


def get_user_playbooks_dir() -> Path:
    """
    Get the user-installed playbooks directory.

    This is where playbooks installed from the repository are stored (read-write).

    Returns:
        Path: Absolute path to ~/.ignition-toolkit/playbooks/ directory

    Example:
        >>> user = get_user_playbooks_dir()
        >>> print(user)
        /root/.ignition-toolkit/playbooks
    """
    user_playbooks = get_user_data_dir() / "playbooks"
    user_playbooks.mkdir(exist_ok=True)
    return user_playbooks


def get_all_playbook_dirs() -> list[Path]:
    """
    Get all playbook directories in priority order.

    User-installed playbooks take priority over built-in playbooks.
    This allows users to override built-in playbooks by installing
    a playbook with the same path.

    Returns:
        list[Path]: List of playbook directories in priority order

    Example:
        >>> dirs = get_all_playbook_dirs()
        >>> print(dirs)
        [Path('/root/.ignition-toolkit/playbooks'), Path('/git/ignition-toolbox/playbooks')]
    """
    return [
        get_user_playbooks_dir(),  # User playbooks have priority
        get_builtin_playbooks_dir()  # Built-in playbooks as fallback
    ]


def get_playbook_path(playbook_name: str) -> Path:
    """
    Get the full path to a playbook file.

    Args:
        playbook_name: Name of the playbook (with or without .yaml extension)

    Returns:
        Path: Absolute path to playbook file

    Example:
        >>> path = get_playbook_path("gateway_login.yaml")
        >>> print(path)
        /git/ignition-toolbox/playbooks/gateway_login.yaml
    """
    if not playbook_name.endswith((".yaml", ".yml")):
        playbook_name = f"{playbook_name}.yaml"

    return get_playbooks_dir() / playbook_name


# === Data Paths ===


def get_data_dir() -> Path:
    """
    Get the data directory for browser artifacts, screenshots, etc.

    When running as a frozen PyInstaller executable, uses the IGNITION_TOOLKIT_DATA
    environment variable (set by Electron) to avoid writing to Program Files.

    Returns:
        Path: Absolute path to data/ directory

    Example:
        >>> data = get_data_dir()
        >>> print(data)
        /git/ignition-toolbox/data
    """
    # Prefer the data directory set by Electron regardless of freeze state
    env_data = os.environ.get("IGNITION_TOOLKIT_DATA")
    if env_data:
        data_dir = Path(env_data)
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    # When running as frozen executable without env var, fall back to home dir
    if is_frozen():
        data_dir = Path.home() / ".ignition-toolkit" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    # Development mode without Electron: use project-relative directory
    data_dir = get_package_root() / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


def get_screenshots_dir() -> Path:
    """
    Get the directory for screenshot storage.

    Returns:
        Path: Absolute path to data/screenshots/ directory

    Example:
        >>> screenshots = get_screenshots_dir()
        >>> print(screenshots)
        /git/ignition-toolbox/data/screenshots
    """
    screenshots_dir = get_data_dir() / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    return screenshots_dir


def get_playwright_browsers_dir() -> Path:
    """
    Get the directory for Playwright browser binaries.

    Returns:
        Path: Absolute path to data/.playwright-browsers/ directory

    Example:
        >>> browsers = get_playwright_browsers_dir()
        >>> print(browsers)
        /git/ignition-toolbox/data/.playwright-browsers
    """
    browsers_dir = get_data_dir() / ".playwright-browsers"
    browsers_dir.mkdir(exist_ok=True)
    return browsers_dir


# === Frontend Paths ===


def get_frontend_dir() -> Path:
    """
    Get the frontend directory.

    Returns:
        Path: Absolute path to frontend/ directory

    Example:
        >>> frontend = get_frontend_dir()
        >>> print(frontend)
        /git/ignition-toolbox/frontend
    """
    return get_package_root() / "frontend"


def get_frontend_dist_dir() -> Path:
    """
    Get the built frontend distribution directory.

    Returns:
        Path: Absolute path to frontend/dist/ directory

    Example:
        >>> dist = get_frontend_dist_dir()
        >>> print(dist)
        /git/ignition-toolbox/frontend/dist
    """
    return get_frontend_dir() / "dist"


# === User Data Paths ===


def get_user_data_dir() -> Path:
    """
    Get the user's data directory for credentials, database, etc.

    Priority order:
    1. IGNITION_TOOLKIT_DATA environment variable (always used in frozen mode)
    2. XDG_DATA_HOME/ignition-toolkit (if XDG_DATA_HOME is set)
    3. ~/.ignition-toolkit/ (fallback)

    Returns:
        Path: Absolute path to user data directory

    Example:
        >>> user_data = get_user_data_dir()
        >>> print(user_data)
        /root/.ignition-toolkit
    """
    # In frozen mode, always use the environment variable from Electron
    # This ensures we never try to write to Program Files
    env_data = os.environ.get("IGNITION_TOOLKIT_DATA")
    if env_data:
        user_dir = Path(env_data)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    # If frozen without env var, use home directory
    if is_frozen():
        user_dir = Path.home() / ".ignition-toolkit"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    # Development mode: use XDG or home directory
    xdg_data_home = os.environ.get("XDG_DATA_HOME")

    if xdg_data_home:
        user_dir = Path(xdg_data_home) / "ignition-toolkit"
    else:
        user_dir = Path.home() / ".ignition-toolkit"

    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_credentials_file() -> Path:
    """
    Get the path to the encrypted credentials vault file.

    Returns:
        Path: Absolute path to credentials.enc file

    Example:
        >>> creds = get_credentials_file()
        >>> print(creds)
        /root/.ignition-toolkit/credentials.enc
    """
    return get_user_data_dir() / "credentials.enc"


def get_database_file() -> Path:
    """
    Get the path to the SQLite database file.

    Returns:
        Path: Absolute path to executions.db file

    Example:
        >>> db = get_database_file()
        >>> print(db)
        /root/.ignition-toolkit/executions.db
    """
    return get_user_data_dir() / "executions.db"


# === Environment-Aware Paths ===


def get_env_file() -> Path:
    """
    Get the path to the .env file.

    Returns:
        Path: Absolute path to .env file

    Example:
        >>> env = get_env_file()
        >>> print(env)
        /git/ignition-toolbox/.env
    """
    return get_package_root() / ".env"


# === Validation ===


def validate_paths() -> dict:
    """
    Validate that all critical paths exist and are accessible.

    Returns:
        dict: Status of each path with 'exists' and 'writable' flags

    Example:
        >>> status = validate_paths()
        >>> print(status['playbooks_dir']['exists'])
        True
    """
    paths_to_check = {
        "package_root": get_package_root(),
        "package_dir": get_package_dir(),
        "playbooks_dir": get_playbooks_dir(),
        "data_dir": get_data_dir(),
        "frontend_dir": get_frontend_dir(),
        "frontend_dist_dir": get_frontend_dist_dir(),
        "user_data_dir": get_user_data_dir(),
        "credentials_file": get_credentials_file(),
        "database_file": get_database_file(),
        "env_file": get_env_file(),
    }

    status = {}
    for name, path in paths_to_check.items():
        status[name] = {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir() if path.exists() else None,
            "is_file": path.is_file() if path.exists() else None,
            "writable": os.access(path.parent if path.is_file() else path, os.W_OK),
        }

    return status


# === Convenience Functions ===


def ensure_directories() -> None:
    """
    Ensure all required directories exist.

    Creates directories if they don't exist:
    - data/
    - data/screenshots/
    - data/.playwright-browsers/
    - ~/.ignition-toolkit/
    - ~/.ignition-toolkit/playbooks/
    """
    get_data_dir()
    get_screenshots_dir()
    get_playwright_browsers_dir()
    get_user_data_dir()
    get_user_playbooks_dir()  # Create user playbooks directory


def get_relative_path(absolute_path: Path) -> Path | None:
    """
    Get a path relative to the package root.

    Args:
        absolute_path: Absolute path to convert

    Returns:
        Path: Relative path from package root, or None if not under package root

    Example:
        >>> abs_path = Path("/git/ignition-toolbox/playbooks/test.yaml")
        >>> rel = get_relative_path(abs_path)
        >>> print(rel)
        playbooks/test.yaml
    """
    try:
        return absolute_path.relative_to(get_package_root())
    except ValueError:
        return None


# === Module Initialization ===

# Ensure directories exist on import
ensure_directories()


# === Public API ===

__all__ = [
    "is_frozen",  # Check if running as PyInstaller executable
    "get_package_root",
    "get_package_dir",
    "get_playbooks_dir",  # Deprecated - use get_builtin_playbooks_dir
    "get_builtin_playbooks_dir",  # NEW: Built-in playbooks
    "get_user_playbooks_dir",  # NEW: User-installed playbooks
    "get_all_playbook_dirs",  # NEW: All playbook directories
    "get_playbook_path",
    "get_data_dir",
    "get_screenshots_dir",
    "get_playwright_browsers_dir",
    "get_frontend_dir",
    "get_frontend_dist_dir",
    "get_user_data_dir",
    "get_credentials_file",
    "get_database_file",
    "get_env_file",
    "validate_paths",
    "ensure_directories",
    "get_relative_path",
]

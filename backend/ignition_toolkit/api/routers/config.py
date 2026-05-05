"""
Configuration and path information API

Provides runtime configuration, dynamic path information, and persistent
UI state storage (e.g. playbook section assignments).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ignition_toolkit.core.config import get_settings
from ignition_toolkit.core.paths import (
    get_package_root,
    get_playbooks_dir,
    get_user_data_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config():
    """
    Get runtime configuration and paths

    Returns dynamic configuration to enable frontend portability.
    Frontend can use these paths instead of hardcoding them.

    Returns:
        dict: Configuration including version, paths, and feature flags
    """
    # Version comes from the package itself; env var allows override for dev/CI
    from ignition_toolkit import __version__
    version = os.getenv("APP_VERSION", __version__)

    # Check if AI is enabled
    ai_enabled = bool(os.getenv("ANTHROPIC_API_KEY"))

    settings = get_settings()

    return {
        "version": version,
        "paths": {
            "playbooks_dir": str(get_playbooks_dir()),
            "package_root": str(get_package_root()),
            "user_data_dir": str(get_user_data_dir()),
        },
        "features": {
            "ai_enabled": ai_enabled,
            "browser_automation": True,
            "designer_automation": False,  # Future feature
        },
        "server": {
            "port": int(os.getenv("API_PORT", "5000")),
            "host": os.getenv("API_HOST", "0.0.0.0"),
        },
        # WebSocket API key: frontend fetches this once at startup via /api/config
        # Electron apps also receive it via IPC (electron/ipc/handlers.ts)
        "websocket_api_key": settings.websocket_api_key,
    }


# ── UI State Persistence ───────────────────────────────────────────────────────

def _ui_state_path() -> Path:
    return get_user_data_dir() / "ui_state.json"


def _load_ui_state() -> dict[str, Any]:
    path = _ui_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ui_state(state: dict[str, Any]) -> None:
    path = _ui_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


class SectionsPayload(BaseModel):
    sections: list[dict[str, Any]]


@router.get("/sections/{domain}")
async def get_sections(domain: str):
    """Return saved playbook sections for a domain."""
    state = _load_ui_state()
    return {"domain": domain, "sections": state.get("sections", {}).get(domain, [])}


@router.put("/sections/{domain}")
async def save_sections(domain: str, payload: SectionsPayload):
    """Persist playbook section assignments for a domain."""
    try:
        state = _load_ui_state()
        if "sections" not in state:
            state["sections"] = {}
        state["sections"][domain] = payload.sections
        _save_ui_state(state)
        return {"status": "ok", "domain": domain, "count": len(payload.sections)}
    except Exception as e:
        logger.exception(f"Failed to save sections for domain '{domain}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
Playbook management routes (Main Router)

Aggregates all playbook-related sub-routers:
- CRUD operations (list, get, update)
- Library operations (install, browse, updates)
- Metadata operations (verify, enable/disable)
- Lifecycle operations (delete, duplicate, import/export)
"""

import logging

from fastapi import APIRouter

# Import individual route functions
from ignition_toolkit.api.routers.playbook_crud import (
    duplicate_playbook as duplicate_playbook_crud,
)
from ignition_toolkit.api.routers.playbook_crud import (
    edit_step,
    get_playbook,
    list_playbooks,
    update_playbook,
    update_playbook_metadata,
)
from ignition_toolkit.api.routers.playbook_library import (
    browse_available_playbooks,
    check_for_updates,
    check_playbook_update,
    delete_github_token_endpoint,
    delete_private_repo_settings_endpoint,
    get_github_token_status,
    get_private_repo_status,
    get_update_stats,
    install_playbook,
    save_github_token_endpoint,
    save_private_repo_settings_endpoint,
    submit_playbook_to_library,
    submit_to_private_repo_endpoint,
    uninstall_playbook,
    update_playbook_to_latest,
)
from ignition_toolkit.api.routers.playbook_lifecycle import (
    create_playbook,
    delete_playbook,
    export_playbook,
    import_playbook,
)
from ignition_toolkit.api.routers.playbook_metadata import (
    disable_playbook,
    enable_playbook,
    mark_playbook_verified,
    reset_all_metadata,
    unmark_playbook_verified,
)

logger = logging.getLogger(__name__)

# Create main router
router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])

# ============================================================================
# CRUD Operations (static routes first, then catch-all)
# ============================================================================

router.add_api_route("", list_playbooks, methods=["GET"], tags=["playbooks-crud"])
router.add_api_route("/update", update_playbook, methods=["PUT"], tags=["playbooks-crud"])
router.add_api_route("/metadata", update_playbook_metadata, methods=["PATCH"], tags=["playbooks-crud"])
router.add_api_route("/edit-step", edit_step, methods=["POST"], tags=["playbooks-crud"])
router.add_api_route("/duplicate", duplicate_playbook_crud, methods=["POST"], tags=["playbooks-crud"])

# ============================================================================
# Library Operations (static routes MUST come before catch-all paths)
# ============================================================================

router.add_api_route("/browse", browse_available_playbooks, methods=["GET"], tags=["playbooks-library"])
router.add_api_route("/install", install_playbook, methods=["POST"], tags=["playbooks-library"])
router.add_api_route("/updates", check_for_updates, methods=["GET"], tags=["playbooks-library"])
router.add_api_route("/updates/stats", get_update_stats, methods=["GET"], tags=["playbooks-library"])
router.add_api_route("/updates/{playbook_path:path}", check_playbook_update, methods=["GET"], tags=["playbooks-library"])
# ============================================================================
# Lifecycle Operations (static routes first)
# ============================================================================

router.add_api_route("/import", import_playbook, methods=["POST"], tags=["playbooks-lifecycle"])
router.add_api_route("/create", create_playbook, methods=["POST"], tags=["playbooks-lifecycle"])
router.add_api_route("/submit", submit_playbook_to_library, methods=["POST"], tags=["playbooks-library"])

# ============================================================================
# GitHub Integration (GET routes must come before the catch-all)
# ============================================================================

router.add_api_route("/github-token", get_github_token_status, methods=["GET"], tags=["playbooks-library"])
router.add_api_route("/github-token", save_github_token_endpoint, methods=["POST"], tags=["playbooks-library"])
router.add_api_route("/github-token", delete_github_token_endpoint, methods=["DELETE"], tags=["playbooks-library"])

router.add_api_route("/private-repo", get_private_repo_status, methods=["GET"], tags=["playbooks-library"])
router.add_api_route("/private-repo", save_private_repo_settings_endpoint, methods=["POST"], tags=["playbooks-library"])
router.add_api_route("/private-repo", delete_private_repo_settings_endpoint, methods=["DELETE"], tags=["playbooks-library"])
router.add_api_route("/private-repo/submit", submit_to_private_repo_endpoint, methods=["POST"], tags=["playbooks-library"])

# ============================================================================
# Metadata Operations (static POST route first)
# ============================================================================

router.add_api_route("/metadata/reset-all", reset_all_metadata, methods=["POST"], tags=["playbooks-metadata"])

# ============================================================================
# CRUD - Catch-all GET route MUST come after all other GET routes.
# Any GET /{path}/suffix registered after this line will be unreachable because
# the :path converter greedily matches slashes, swallowing the suffix.
# ============================================================================

# Export must be registered before the catch-all GET.
router.add_api_route("/{playbook_path:path}/export", export_playbook, methods=["GET"], tags=["playbooks-lifecycle"])

router.add_api_route("/{playbook_path:path}", get_playbook, methods=["GET"], tags=["playbooks-crud"])

# ============================================================================
# Path-based operations (non-GET methods — safe to register after catch-all)
# ============================================================================

router.add_api_route("/{playbook_path:path}", delete_playbook, methods=["DELETE"], tags=["playbooks-lifecycle"])
router.add_api_route("/{playbook_path:path}/uninstall", uninstall_playbook, methods=["DELETE"], tags=["playbooks-library"])
router.add_api_route("/{playbook_path:path}/update", update_playbook_to_latest, methods=["POST"], tags=["playbooks-library"])
router.add_api_route("/{playbook_path:path}/verify", mark_playbook_verified, methods=["POST"], tags=["playbooks-metadata"])
router.add_api_route("/{playbook_path:path}/unverify", unmark_playbook_verified, methods=["POST"], tags=["playbooks-metadata"])
router.add_api_route("/{playbook_path:path}/enable", enable_playbook, methods=["POST"], tags=["playbooks-metadata"])
router.add_api_route("/{playbook_path:path}/disable", disable_playbook, methods=["POST"], tags=["playbooks-metadata"])

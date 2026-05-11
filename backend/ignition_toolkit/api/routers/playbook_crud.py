"""
Playbook CRUD operations router

Handles basic playbook operations: list, get, update YAML content,
update metadata (name/description), and edit steps.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ignition_toolkit.api.routers.models import ParameterInfo, PlaybookInfo, StepInfo
from ignition_toolkit.core.paths import (
    get_all_playbook_dirs,
    get_builtin_playbooks_dir,
    get_data_dir,
    get_playbooks_dir,
    get_user_playbooks_dir,
    is_frozen,
)
from ignition_toolkit.core.timeouts import TimeoutKeys
from ignition_toolkit.core.validation_limits import ValidationLimits
from ignition_toolkit.playbook.loader import PlaybookLoader
from ignition_toolkit.playbook.step_type_registry import get_step_definition_by_value

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


def _ensure_writable_playbook(playbook_path: Path) -> Path:
    """
    Ensure a playbook is in a writable location.

    If the playbook is in the read-only built-in directory (e.g., Program Files),
    copy it to the user playbooks directory first.

    Returns the writable path (may be the same or the new user copy).
    """
    if not is_frozen():
        return playbook_path

    builtin_dir = get_builtin_playbooks_dir().resolve()
    try:
        rel = playbook_path.resolve().relative_to(builtin_dir)
    except ValueError:
        # Already in user dir or elsewhere — assume writable
        return playbook_path

    # Copy to user playbooks dir, preserving subdirectory structure
    user_path = get_user_playbooks_dir() / rel
    user_path.parent.mkdir(parents=True, exist_ok=True)
    if not user_path.exists():
        shutil.copy2(playbook_path, user_path)
        logger.info(f"Copied built-in playbook to user dir: {user_path}")
    return user_path


def _get_backup_dir() -> Path:
    """Get a writable directory for playbook backups."""
    backup_dir = get_data_dir() / "playbook_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


# ============================================================================
# Pydantic Models
# ============================================================================


class PlaybookUpdateRequest(BaseModel):
    """Request to update a playbook YAML file"""

    playbook_path: str  # Relative path from playbooks directory
    yaml_content: str  # New YAML content


class PlaybookMetadataUpdateRequest(BaseModel):
    """Request to update playbook name and description

    SECURITY: Includes input validation to prevent XSS, injection attacks, and DoS
    """

    playbook_path: str
    name: str | None = None
    description: str | None = None

    @field_validator('playbook_path')
    @classmethod
    def validate_playbook_path_field(cls, v: str) -> str:
        """Validate playbook path field"""
        if not v or not v.strip():
            raise ValueError("Playbook path cannot be empty")
        if len(v) > ValidationLimits.PLAYBOOK_PATH_MAX:
            raise ValueError(f"Playbook path too long (max {ValidationLimits.PLAYBOOK_PATH_MAX} characters)")
        return v.strip()

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Validate playbook name for security and sanity"""
        if v is None:
            return v

        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or whitespace")

        if len(v) > ValidationLimits.PLAYBOOK_NAME_MAX:
            raise ValueError(f"Name too long (max {ValidationLimits.PLAYBOOK_NAME_MAX} characters)")

        dangerous_chars = ['<', '>', '"', "'", '`', '{', '}', '$', '|', '&', ';']
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Name contains invalid character: {char}")

        if any(ord(c) < 32 for c in v):
            raise ValueError("Name contains control characters")

        return v

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Validate playbook description for security"""
        if v is None:
            return v

        v = v.strip()

        if len(v) > ValidationLimits.PLAYBOOK_DESCRIPTION_MAX:
            raise ValueError(f"Description too long (max {ValidationLimits.PLAYBOOK_DESCRIPTION_MAX} characters)")

        dangerous_patterns = ['<script', 'javascript:', 'onerror=', 'onload=', '<?php']
        v_lower = v.lower()
        for pattern in dangerous_patterns:
            if pattern in v_lower:
                raise ValueError(f"Description contains potentially dangerous pattern: {pattern}")

        for c in v:
            if ord(c) < 32 and c not in ['\n', '\r', '\t']:
                raise ValueError("Description contains invalid control characters")

        return v


class StepEditRequest(BaseModel):
    """Request to edit a step in a playbook"""

    playbook_path: str
    step_id: str
    new_parameters: dict[str, Any]


# ============================================================================
# Helper Functions
# ============================================================================


def get_metadata_store():
    """Get shared metadata store from app"""
    from ignition_toolkit.api.app import metadata_store
    return metadata_store


def _get_relative_to_any_playbook_dir(full_path: Path) -> str:
    """Get relative path from whichever playbook directory contains this path."""
    resolved = full_path.resolve()
    for playbook_dir in get_all_playbook_dirs():
        try:
            return str(resolved.relative_to(playbook_dir.resolve()))
        except ValueError:
            continue
    # Fallback to built-in dir (original behavior)
    return str(resolved.relative_to(get_playbooks_dir().resolve()))


def validate_playbook_path(path_str: str) -> Path:
    """
    Validate playbook path to prevent directory traversal attacks

    SECURITY: This is a wrapper around PathValidator for backwards compatibility.
    Searches across all playbook directories (user first, then built-in).

    Args:
        path_str: User-provided playbook path

    Returns:
        Validated absolute Path

    Raises:
        HTTPException: If path is invalid or outside playbooks directory
    """
    from ignition_toolkit.core.validation import PathValidator

    # Search all playbook directories (user dir first, then built-in)
    for playbook_dir in get_all_playbook_dirs():
        try:
            return PathValidator.validate_playbook_path(
                path_str,
                base_dir=playbook_dir,
                must_exist=True
            )
        except HTTPException:
            continue

    # If not found in any directory, raise 404
    raise HTTPException(status_code=404, detail=f"Playbook file not found: {path_str}")


def _compute_relevant_timeouts(steps, playbook_dirs, domain=None) -> list[str]:
    """
    Analyze playbook step types to determine which timeout categories are relevant.

    Inspects each step's type via the unified step type registry, and for
    playbook.run steps resolves the nested playbook one level deep to union
    its timeout categories too.

    Returns a sorted list of applicable timeout category strings:
        "browser_operation", "designer_launch", "gateway_restart", "module_install"
    """
    result = set()

    for step in steps:
        step_type_value = step.type.value  # e.g. "browser.click", "gateway.restart"

        if step_type_value == "playbook.run":
            # Resolve nested playbook one level deep
            nested_path = step.parameters.get("playbook")
            if nested_path:
                try:
                    nested_file = None
                    for playbook_dir in playbook_dirs:
                        candidate = playbook_dir / nested_path
                        if candidate.exists():
                            nested_file = candidate
                            break
                    if nested_file:
                        nested_loader = PlaybookLoader()
                        nested_playbook = nested_loader.load_from_file(nested_file)
                        for nested_step in nested_playbook.steps:
                            defn = get_step_definition_by_value(nested_step.type.value)
                            if defn and defn.timeout_category:
                                result.add(defn.timeout_category)
                except Exception:
                    pass  # Skip silently on any error (missing file, parse error, etc.)
        else:
            defn = get_step_definition_by_value(step_type_value)
            if defn and defn.timeout_category:
                result.add(defn.timeout_category)

    # Designer domain playbooks use designer_launch timeout
    if domain == "designer":
        result.add(TimeoutKeys.DESIGNER_LAUNCH)

    return sorted(result)


# ============================================================================
# Routes
# ============================================================================


@router.get("", response_model=list[PlaybookInfo])
async def list_playbooks():
    """
    List all available playbooks from all sources.

    Scans both built-in and user-installed playbook directories.
    User playbooks take priority over built-in playbooks with the same path.
    """
    metadata_store = get_metadata_store()

    playbook_dirs = get_all_playbook_dirs()
    builtin_dir = get_builtin_playbooks_dir()
    user_dir = get_user_playbooks_dir()

    seen_paths = set()
    playbooks = []

    for playbooks_dir in playbook_dirs:
        if not playbooks_dir.exists():
            continue

        if playbooks_dir == builtin_dir:
            source = "built-in"
        elif playbooks_dir == user_dir:
            source = "user-installed"
        else:
            source = "unknown"

        for yaml_file in playbooks_dir.rglob("*.yaml"):
            if ".backup." in yaml_file.name:
                continue

            try:
                loader = PlaybookLoader()
                playbook = loader.load_from_file(yaml_file)

                # Normalize path to use forward slashes for consistency across platforms
                relative_path = str(yaml_file.relative_to(playbooks_dir)).replace("\\", "/")

                # Auto-sync: if user-dir copy exists for a built-in playbook
                # and user never edited it (revision 0), update from built-in
                if source == "user-installed" and builtin_dir:
                    builtin_file = builtin_dir / relative_path
                    if builtin_file.exists():
                        meta = metadata_store.get_metadata(relative_path)
                        if meta.revision == 0 and meta.origin in ("built-in", "unknown"):
                            if builtin_file.read_bytes() != yaml_file.read_bytes():
                                shutil.copy2(builtin_file, yaml_file)
                                logger.info(f"Auto-synced playbook from built-in: {relative_path}")
                                playbook = loader.load_from_file(yaml_file)
                    else:
                        # Cleanup: built-in was removed — delete unedited user-dir copy
                        meta = metadata_store.get_metadata(relative_path)
                        if meta.revision == 0 and meta.origin in ("built-in", "unknown"):
                            yaml_file.unlink()
                            metadata_store.delete_metadata(relative_path)
                            logger.info(f"Removed obsolete user-dir playbook (built-in deleted): {relative_path}")
                            continue

                if relative_path in seen_paths:
                    logger.debug(f"Skipping {relative_path} from {source} (already loaded)")
                    continue

                seen_paths.add(relative_path)

                parameters = [
                    ParameterInfo(
                        name=p.name,
                        type=p.type.value,
                        required=p.required,
                        default=str(p.default) if p.default is not None else None,
                        description=p.description,
                    )
                    for p in playbook.parameters
                ]

                steps = [
                    StepInfo(
                        id=s.id,
                        name=s.name,
                        type=s.type.value,
                        timeout=s.timeout,
                        retry_count=s.retry_count,
                    )
                    for s in playbook.steps
                ]

                meta = metadata_store.get_metadata(relative_path)

                # Metadata store is the source of truth for verified status
                # YAML verified field is only used to initialize on first load (when origin is unknown)
                if meta.origin == "unknown":
                    # First time seeing this playbook - check YAML for initial verified state
                    yaml_verified = playbook.metadata.get("verified")
                    if yaml_verified and not meta.verified:
                        meta.verified = True
                        meta.verified_by = "yaml"
                        metadata_store.update_metadata(relative_path, meta)

                verified_status = meta.verified

                if meta.origin == "unknown":
                    meta.origin = source
                    metadata_store.update_metadata(relative_path, meta)

                relevant_timeouts = _compute_relevant_timeouts(playbook.steps, playbook_dirs, domain=playbook.metadata.get("domain"))

                playbooks.append(
                    PlaybookInfo(
                        name=playbook.name,
                        path=relative_path,
                        version=playbook.version,
                        description=playbook.description,
                        parameter_count=len(playbook.parameters),
                        step_count=len(playbook.steps),
                        parameters=parameters,
                        steps=steps,
                        domain=playbook.metadata.get("domain"),
                        group=playbook.metadata.get("group"),
                        revision=meta.revision,
                        verified=verified_status,
                        enabled=meta.enabled,
                        last_modified=meta.last_modified,
                        verified_at=meta.verified_at,
                        last_committed_at=meta.last_committed_at,
                        origin=meta.origin,
                        duplicated_from=meta.duplicated_from,
                        created_at=meta.created_at,
                        relevant_timeouts=relevant_timeouts,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to load playbook {yaml_file}: {e}")
                try:
                    relative_path = str(yaml_file.relative_to(playbooks_dir)).replace("\\", "/")
                    if relative_path not in seen_paths:
                        seen_paths.add(relative_path)
                        meta = metadata_store.get_metadata(relative_path)
                        name = yaml_file.stem.replace("_", " ").replace("-", " ").title()
                        playbooks.append(PlaybookInfo(
                            name=name,
                            path=relative_path,
                            version="?",
                            description="",
                            parameter_count=0,
                            step_count=0,
                            revision=meta.revision,
                            enabled=meta.enabled,
                            verified=False,
                            last_modified=meta.last_modified,
                            last_committed_at=meta.last_committed_at,
                            origin=meta.origin,
                            created_at=meta.created_at,
                            load_error=str(e),
                        ))
                except Exception:
                    pass
                continue

    return playbooks


@router.get("/{playbook_path:path}", response_model=PlaybookInfo)
async def get_playbook(playbook_path: str):
    """Get detailed playbook information including full parameter schema"""
    metadata_store = get_metadata_store()
    try:
        validated_path = validate_playbook_path(playbook_path)

        loader = PlaybookLoader()
        playbook = loader.load_from_file(validated_path)

        parameters = [
            ParameterInfo(
                name=p.name,
                type=p.type.value,
                required=p.required,
                default=str(p.default) if p.default is not None else None,
                description=p.description,
            )
            for p in playbook.parameters
        ]

        steps = [
            StepInfo(
                id=s.id,
                name=s.name,
                type=s.type.value,
                timeout=s.timeout,
                retry_count=s.retry_count,
            )
            for s in playbook.steps
        ]

        relative_path = _get_relative_to_any_playbook_dir(validated_path)
        meta = metadata_store.get_metadata(relative_path)

        playbook_dirs = get_all_playbook_dirs()
        relevant_timeouts = _compute_relevant_timeouts(playbook.steps, playbook_dirs, domain=playbook.metadata.get("domain"))

        return PlaybookInfo(
            name=playbook.name,
            path=relative_path,
            version=playbook.version,
            description=playbook.description,
            parameter_count=len(playbook.parameters),
            step_count=len(playbook.steps),
            parameters=parameters,
            steps=steps,
            domain=playbook.metadata.get("domain"),
            group=playbook.metadata.get("group"),
            revision=meta.revision,
            verified=meta.verified,
            enabled=meta.enabled,
            last_modified=meta.last_modified,
            verified_at=meta.verified_at,
            last_committed_at=meta.last_committed_at,
            origin=meta.origin,
            duplicated_from=meta.duplicated_from,
            created_at=meta.created_at,
            relevant_timeouts=relevant_timeouts,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Playbook not found: {e}")


@router.put("/update")
async def update_playbook(request: PlaybookUpdateRequest):
    """
    Update a playbook YAML file with new content

    This is used when applying fixes from debug mode.
    Creates a backup before updating.
    """
    metadata_store = get_metadata_store()
    try:
        playbook_path = validate_playbook_path(request.playbook_path)

        # Save backup to writable directory
        backup_dir = _get_backup_dir()
        backup_name = f"{playbook_path.stem}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        backup_path = backup_dir / backup_name
        backup_path.write_text(playbook_path.read_text(encoding='utf-8'), encoding='utf-8')
        logger.info(f"Created backup: {backup_path}")

        try:
            yaml.safe_load(request.yaml_content)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

        # Ensure we write to a writable location
        writable_path = _ensure_writable_playbook(playbook_path)
        writable_path.write_text(request.yaml_content, encoding='utf-8')
        logger.info(f"Updated playbook: {writable_path}")

        metadata_store.increment_revision(request.playbook_path)
        meta = metadata_store.get_metadata(request.playbook_path)

        return {
            "status": "success",
            "playbook_path": str(request.playbook_path),
            "backup_path": str(backup_path.name),
            "revision": meta.revision,
            "message": f"Playbook updated successfully (revision {meta.revision})",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/metadata")
async def update_playbook_metadata(request: PlaybookMetadataUpdateRequest):
    """Update playbook name and/or description in YAML file"""
    metadata_store = get_metadata_store()
    try:
        playbook_path = validate_playbook_path(request.playbook_path)

        if not playbook_path.exists():
            raise HTTPException(status_code=404, detail="Playbook not found")

        with open(playbook_path, encoding='utf-8') as f:
            playbook_data = yaml.safe_load(f)

        if request.name is not None:
            playbook_data["name"] = request.name
        if request.description is not None:
            playbook_data["description"] = request.description

        # Save backup to writable directory
        backup_dir = _get_backup_dir()
        backup_name = f"{playbook_path.stem}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        backup_path = backup_dir / backup_name
        backup_path.write_text(playbook_path.read_text(encoding='utf-8'), encoding='utf-8')

        # Ensure we write to a writable location
        writable_path = _ensure_writable_playbook(playbook_path)
        with open(writable_path, "w", encoding='utf-8') as f:
            yaml.safe_dump(playbook_data, f, default_flow_style=False, sort_keys=False)

        metadata_store.increment_revision(request.playbook_path)
        meta = metadata_store.get_metadata(request.playbook_path)

        logger.info(f"Updated playbook metadata: {writable_path}")

        return {
            "status": "success",
            "playbook_path": str(request.playbook_path),
            "name": playbook_data.get("name"),
            "description": playbook_data.get("description"),
            "revision": meta.revision,
            "message": "Playbook metadata updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating playbook metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PlaybookDuplicateRequest(BaseModel):
    """Request to duplicate a playbook"""
    playbook_path: str  # Relative path of playbook to duplicate
    new_name: str | None = None  # Optional new name (defaults to "Original Name (Copy)")


@router.post("/duplicate")
async def duplicate_playbook(request: PlaybookDuplicateRequest):
    """
    Duplicate a playbook to the user playbooks directory.

    Creates a copy of the playbook with "(Copy)" suffix in the name.
    The new playbook is saved to the user-installed playbooks directory.
    """
    metadata_store = get_metadata_store()
    try:
        # Validate source path
        source_path = validate_playbook_path(request.playbook_path)

        if not source_path.exists():
            raise HTTPException(status_code=404, detail="Source playbook not found")

        # Load original playbook
        with open(source_path, encoding='utf-8') as f:
            playbook_data = yaml.safe_load(f)

        original_name = playbook_data.get("name", "Untitled")

        # Set new name
        if request.new_name:
            new_name = request.new_name
        else:
            new_name = f"{original_name} (Copy)"

        playbook_data["name"] = new_name

        # Remove verified status from copy (user must verify their modifications)
        if "verified" in playbook_data:
            del playbook_data["verified"]
        if "metadata" in playbook_data and "verified" in playbook_data["metadata"]:
            del playbook_data["metadata"]["verified"]

        # Determine destination path in user playbooks directory
        user_dir = get_user_playbooks_dir()
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create filename from new name (sanitize for filesystem)
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in new_name)
        safe_name = safe_name.strip().replace(" ", "_")

        # Preserve subdirectory structure if original is in a subdomain folder
        source_relative = Path(request.playbook_path)
        if len(source_relative.parts) > 1:
            # Has subdirectory (e.g., "gateway/backup.yaml")
            dest_subdir = user_dir / source_relative.parent
            dest_subdir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_subdir / f"{safe_name}.yaml"
        else:
            dest_path = user_dir / f"{safe_name}.yaml"

        # Ensure unique filename
        counter = 1
        original_dest_path = dest_path
        while dest_path.exists():
            stem = original_dest_path.stem
            dest_path = original_dest_path.with_name(f"{stem}_{counter}.yaml")
            counter += 1

        # Write new playbook
        with open(dest_path, "w", encoding='utf-8') as f:
            yaml.safe_dump(playbook_data, f, default_flow_style=False, sort_keys=False)

        # Calculate relative path for metadata
        relative_path = str(dest_path.relative_to(user_dir)).replace("\\", "/")

        # Update metadata store
        meta = metadata_store.get_metadata(relative_path)
        meta.origin = "user-installed"
        meta.duplicated_from = request.playbook_path
        meta.created_at = datetime.now().isoformat()
        meta.verified = False  # User must verify their modifications
        metadata_store.update_metadata(relative_path, meta)

        logger.info(f"Duplicated playbook: {source_path} -> {dest_path}")

        return {
            "status": "success",
            "original_path": request.playbook_path,
            "new_path": relative_path,
            "new_name": new_name,
            "message": f"Playbook duplicated successfully as '{new_name}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error duplicating playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edit-step")
async def edit_step(request: StepEditRequest):
    """Edit a step's parameters in a playbook during execution"""
    try:
        playbook_path = validate_playbook_path(request.playbook_path)

        with open(playbook_path, encoding='utf-8') as f:
            playbook_data = yaml.safe_load(f)

        step_found = False
        for step in playbook_data.get("steps", []):
            if step.get("id") == request.step_id:
                if "parameters" not in step:
                    step["parameters"] = {}
                step["parameters"].update(request.new_parameters)
                step_found = True
                break

        if not step_found:
            raise HTTPException(status_code=404, detail=f"Step not found: {request.step_id}")

        # Ensure we write to a writable location
        writable_path = _ensure_writable_playbook(playbook_path)
        with open(writable_path, "w", encoding='utf-8') as f:
            yaml.safe_dump(playbook_data, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Updated step '{request.step_id}' in {writable_path}")
        return {"message": "Step updated", "step_id": request.step_id}

    except Exception as e:
        logger.exception(f"Step edit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

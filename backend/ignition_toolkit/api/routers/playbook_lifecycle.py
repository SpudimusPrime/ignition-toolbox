"""
Playbook lifecycle operations router

Handles playbook lifecycle: delete, duplicate, export, import, and create.
"""

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ignition_toolkit.core.paths import (
    get_all_playbook_dirs,
    get_playbooks_dir,
    get_user_playbooks_dir,
)
from ignition_toolkit.playbook.loader import PlaybookLoader

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================


class PlaybookExportResponse(BaseModel):
    """Response for playbook export containing YAML content"""
    name: str
    path: str
    version: str
    description: str
    domain: str
    yaml_content: str
    metadata: dict[str, Any]


class PlaybookImportRequest(BaseModel):
    """Request to import a playbook from JSON"""
    name: str
    domain: str  # gateway, perspective, or designer
    yaml_content: str
    overwrite: bool = False
    metadata: dict[str, Any] | None = None  # Optional metadata from export


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
    Validate playbook path to prevent directory traversal attacks.
    Searches across all playbook directories (user first, then built-in).

    Args:
        path_str: User-provided playbook path

    Returns:
        Validated absolute Path

    Raises:
        HTTPException: If path is invalid or outside playbooks directory
    """
    from ignition_toolkit.core.validation import PathValidator

    for playbook_dir in get_all_playbook_dirs():
        try:
            return PathValidator.validate_playbook_path(
                path_str,
                base_dir=playbook_dir,
                must_exist=True
            )
        except HTTPException:
            continue

    raise HTTPException(status_code=404, detail=f"Playbook file not found: {path_str}")


def get_relative_playbook_path(path_str: str) -> str:
    """
    Convert a playbook path (full or relative) to a relative path from playbooks directory.
    Searches across all playbook directories (user first, then built-in).

    Args:
        path_str: User-provided playbook path (can be full or relative)

    Returns:
        Relative path string from playbooks directory
    """
    from ignition_toolkit.core.validation import PathValidator

    for playbook_dir in get_all_playbook_dirs():
        try:
            resolved_dir = playbook_dir.resolve()
            validated_path = PathValidator.validate_playbook_path(
                path_str,
                base_dir=resolved_dir,
                must_exist=False
            )
            relative_path = validated_path.relative_to(resolved_dir)
            return str(relative_path)
        except HTTPException:
            continue

    if ".." not in path_str and not Path(path_str).is_absolute():
        return path_str
    raise HTTPException(
        status_code=400,
        detail="Invalid playbook path - must be relative path within playbooks directory"
    )


# ============================================================================
# Routes
# ============================================================================


@router.delete("/{playbook_path:path}")
async def delete_playbook(playbook_path: str):
    """Delete a playbook file and its metadata"""
    metadata_store = get_metadata_store()
    try:
        full_path = validate_playbook_path(playbook_path)

        if not full_path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {playbook_path}")

        os.remove(full_path)
        logger.info(f"Deleted playbook file: {full_path}")

        relative_path = get_relative_playbook_path(playbook_path)
        try:
            metadata = metadata_store.get_metadata(relative_path)
            if metadata:
                if relative_path in metadata_store._metadata:
                    del metadata_store._metadata[relative_path]
                    metadata_store._save()
                    logger.info(f"Deleted metadata for: {relative_path}")
        except Exception as meta_error:
            logger.warning(f"Could not delete metadata: {meta_error}")

        return {"status": "success", "message": f"Playbook deleted: {playbook_path}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_path:path}/duplicate")
async def duplicate_playbook(playbook_path: str, new_name: str | None = None):
    """
    Duplicate a playbook with a new name

    Creates a copy of the playbook in the same directory with a new name.
    Marks the new playbook as duplicated from the source.

    Args:
        playbook_path: Source playbook path (relative to playbooks dir)
        new_name: Optional new playbook name for the duplicate (user-provided)

    Returns:
        dict: New playbook info with path and metadata
    """
    metadata_store = get_metadata_store()

    try:
        source_path = validate_playbook_path(playbook_path)

        if not source_path.is_file():
            raise HTTPException(status_code=400, detail=f"Source is not a file: {playbook_path}")

        source_stem = source_path.stem  # filename without extension
        source_suffix = source_path.suffix  # .yaml or .yml

        if new_name:
            # User provided a name - use it directly
            new_stem = new_name.replace(source_suffix, "")  # Remove extension if included
            # Sanitize: convert to snake_case
            new_stem = re.sub(r'[^a-zA-Z0-9_]', '_', new_stem.lower())
            new_stem = re.sub(r'_+', '_', new_stem).strip('_')
        else:
            # No name provided - extract base name (remove existing _copy suffixes)
            base_stem = re.sub(r'(_copy)+(_\d+)?$', '', source_stem)
            new_stem = f"{base_stem}_copy"

        # Always write duplicates to the writable user directory
        # Preserve the domain subdirectory from the source path
        source_relative = _get_relative_to_any_playbook_dir(source_path)
        target_parent = get_user_playbooks_dir() / Path(source_relative).parent
        target_parent.mkdir(parents=True, exist_ok=True)

        new_path = target_parent / f"{new_stem}{source_suffix}"
        counter = 1
        while new_path.exists():
            stem_for_counter = new_stem.rstrip('0123456789_') if new_name else re.sub(r'(_copy)+(_\d+)?$', '', source_stem) + "_copy"
            new_path = target_parent / f"{stem_for_counter}_{counter}{source_suffix}"
            counter += 1

        shutil.copy2(source_path, new_path)
        logger.info(f"Duplicated playbook: {source_path} -> {new_path}")

        source_relative = _get_relative_to_any_playbook_dir(source_path)
        new_relative = _get_relative_to_any_playbook_dir(new_path)

        metadata_store.mark_as_duplicated(new_relative, source_relative)
        logger.info(f"Marked {new_relative} as duplicated from {source_relative}")

        loader = PlaybookLoader()
        new_playbook = loader.load_from_file(new_path)

        domain = new_playbook.metadata.get("domain")

        return {
            "status": "success",
            "message": "Playbook duplicated successfully",
            "source_path": source_relative,
            "new_path": new_relative,
            "playbook": {
                "path": new_relative,
                "name": new_playbook.name,
                "description": new_playbook.description,
                "version": new_playbook.version,
                "domain": domain,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error duplicating playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_path:path}/export", response_model=PlaybookExportResponse)
async def export_playbook(playbook_path: str):
    """
    Export a playbook with full YAML content

    Returns JSON with playbook metadata and YAML content for portability
    """
    try:
        validated_path = validate_playbook_path(playbook_path)

        with open(validated_path, encoding='utf-8') as f:
            yaml_content = f.read()

        relative_path = _get_relative_to_any_playbook_dir(validated_path)
        metadata_store = get_metadata_store()
        meta = metadata_store.get_metadata(relative_path)

        # Try to parse for full metadata — fall back to filename-derived values if invalid
        try:
            loader = PlaybookLoader()
            playbook = loader.load_from_file(validated_path)
            name = playbook.name
            version = playbook.version
            description = playbook.description
            domain = playbook.metadata.get('domain', 'gateway')
        except Exception as parse_err:
            logger.warning(f"Exporting invalid playbook {playbook_path}: {parse_err}")
            name = validated_path.stem.replace("_", " ").replace("-", " ").title()
            version = "?"
            description = ""
            domain = "unknown"

        return PlaybookExportResponse(
            name=name,
            path=relative_path,
            version=version,
            description=description,
            domain=domain,
            yaml_content=yaml_content,
            metadata={
                'revision': meta.revision,
                'verified': meta.verified,
                'verified_at': meta.verified_at,
                'verified_by': meta.verified_by,
                'origin': meta.origin,
                'created_at': meta.created_at,
                'exported_at': datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error exporting playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_playbook(request: PlaybookImportRequest):
    """
    Import a playbook from JSON export

    Creates a new playbook file in the appropriate domain directory.
    If a playbook with the same name exists, either overwrites or creates a copy.
    """
    metadata_store = get_metadata_store()
    try:
        if request.domain not in ['gateway', 'perspective', 'designer']:
            raise HTTPException(status_code=400, detail=f"Invalid domain: {request.domain}")

        try:
            yaml.safe_load(request.yaml_content)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

        # Always write new/imported playbooks to the writable user directory
        playbooks_dir = get_user_playbooks_dir()
        target_dir = playbooks_dir / request.domain
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = request.name.lower().replace(' ', '_').replace('-', '_')
        safe_name = re.sub(r'[^a-z0-9_]', '', safe_name)

        target_file = target_dir / f"{safe_name}.yaml"

        if target_file.exists() and not request.overwrite:
            counter = 1
            while target_file.exists():
                target_file = target_dir / f"{safe_name}_{counter}.yaml"
                counter += 1

        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(request.yaml_content)

        logger.info(f"Imported playbook to: {target_file}")

        relative_path = str(target_file.relative_to(playbooks_dir))
        metadata_store.mark_as_imported(relative_path)

        if request.metadata and request.metadata.get('verified'):
            metadata_store.mark_verified(
                relative_path,
                verified_by=request.metadata.get('verified_by', 'imported')
            )
            logger.info(f"Restored verified status for imported playbook: {relative_path}")

        loader = PlaybookLoader()
        new_playbook = loader.load_from_file(target_file)

        return {
            "status": "success",
            "message": "Playbook imported successfully",
            "path": relative_path,
            "playbook": {
                "name": new_playbook.name,
                "path": relative_path,
                "version": new_playbook.version,
                "description": new_playbook.description,
                "domain": request.domain,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error importing playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_playbook(request: PlaybookImportRequest):
    """
    Create a new blank playbook or from template

    Same as import but intended for creating new playbooks from scratch
    """
    return await import_playbook(request)

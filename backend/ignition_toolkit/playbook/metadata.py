"""
Playbook metadata management

Tracks playbook versions, verification status, and enabled/disabled state.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PlaybookMetadata:
    """Metadata for a playbook"""

    playbook_path: str  # Relative path from playbooks directory
    version: str = "1.0.0"
    revision: int = 0
    verified: bool = False
    enabled: bool = True
    last_modified: str | None = None
    verified_at: str | None = None
    verified_by: str | None = None
    notes: str = ""
    # PORTABILITY v4: Origin tracking for playbook management
    origin: str = "unknown"  # built-in, user-created, duplicated
    duplicated_from: str | None = None  # Source playbook path if duplicated
    created_at: str | None = None  # When playbook was created/added
    last_committed_at: str | None = None  # When last pushed to private repo

    def increment_revision(self):
        """Increment revision number"""
        self.revision += 1
        self.last_modified = datetime.now().isoformat()

    def mark_verified(self, verified_by: str = "user"):
        """Mark playbook as verified"""
        self.verified = True
        self.verified_at = datetime.now().isoformat()
        self.verified_by = verified_by

    def unmark_verified(self):
        """Unmark playbook as verified"""
        self.verified = False
        self.verified_at = None
        self.verified_by = None

    def mark_committed(self):
        """Record that this playbook was successfully pushed to the private repo"""
        self.last_committed_at = datetime.now().isoformat()

    def mark_as_built_in(self):
        """Mark playbook as built-in (shipped with toolkit)"""
        self.origin = "built-in"
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def mark_as_user_created(self):
        """Mark playbook as user-created (new playbook)"""
        self.origin = "user-created"
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def mark_as_duplicated(self, source_path: str):
        """Mark playbook as duplicated from another playbook"""
        self.origin = "duplicated"
        self.duplicated_from = source_path
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class PlaybookMetadataStore:
    """
    Manage playbook metadata in a JSON file

    Stores metadata separately from YAML playbooks to avoid polluting
    version control with runtime state.
    """

    def __init__(self, metadata_file: Path = None):
        """
        Initialize metadata store

        Args:
            metadata_file: Path to metadata JSON file
                          (default: uses get_toolkit_data_dir()/playbook_metadata.json)
        """
        if metadata_file is None:
            # Use the toolkit data directory which respects IGNITION_TOOLKIT_DATA env var
            from ignition_toolkit.config import get_toolkit_data_dir

            config_dir = get_toolkit_data_dir()
            config_dir.mkdir(parents=True, exist_ok=True)
            metadata_file = config_dir / "playbook_metadata.json"

        self.metadata_file = metadata_file
        self._metadata: dict[str, PlaybookMetadata] = {}
        self._load()

    def _load(self):
        """Load metadata from file"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, encoding='utf-8') as f:
                    data = json.load(f)
                    self._metadata = {path: PlaybookMetadata(**meta) for path, meta in data.items()}
                logger.debug(f"Loaded metadata for {len(self._metadata)} playbooks")
            except Exception as e:
                logger.error(f"Error loading playbook metadata: {e}")
                self._metadata = {}
        else:
            logger.debug("No existing metadata file, starting fresh")

    def _save(self):
        """Save metadata to file"""
        try:
            data = {path: asdict(meta) for path, meta in self._metadata.items()}
            with open(self.metadata_file, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved metadata for {len(self._metadata)} playbooks")
        except Exception as e:
            logger.error(f"Error saving playbook metadata: {e}")

    def _normalize_path(self, playbook_path: str) -> str:
        """
        Normalize playbook path to use forward slashes consistently.

        This ensures paths work the same on Windows and Unix, and that
        paths stored with backslashes can be found with forward slashes.
        """
        # Always use forward slashes for consistency
        return playbook_path.replace("\\", "/")

    def get_metadata(self, playbook_path: str) -> PlaybookMetadata:
        """
        Get metadata for a playbook (creates default if not exists)

        Args:
            playbook_path: Relative path from playbooks directory

        Returns:
            Playbook metadata
        """
        # Normalize path to use forward slashes
        normalized_path = self._normalize_path(playbook_path)

        if normalized_path not in self._metadata:
            self._metadata[normalized_path] = PlaybookMetadata(playbook_path=normalized_path)
            self._save()
        return self._metadata[normalized_path]

    def update_metadata(self, playbook_path: str, metadata: PlaybookMetadata):
        """
        Update metadata for a playbook

        Args:
            playbook_path: Relative path from playbooks directory
            metadata: Updated metadata
        """
        normalized_path = self._normalize_path(playbook_path)
        # Also normalize the path stored in the metadata object
        metadata.playbook_path = normalized_path
        self._metadata[normalized_path] = metadata
        self._save()

    def increment_revision(self, playbook_path: str):
        """
        Increment playbook revision

        Args:
            playbook_path: Relative path from playbooks directory
        """
        normalized_path = self._normalize_path(playbook_path)
        metadata = self.get_metadata(normalized_path)
        metadata.increment_revision()
        self.update_metadata(normalized_path, metadata)
        logger.info(f"Incremented revision for {normalized_path} to r{metadata.revision}")

    def mark_verified(self, playbook_path: str, verified_by: str = "user"):
        """
        Mark playbook as verified

        Args:
            playbook_path: Relative path from playbooks directory
            verified_by: Who verified the playbook
        """
        normalized_path = self._normalize_path(playbook_path)
        metadata = self.get_metadata(normalized_path)
        metadata.mark_verified(verified_by)
        self.update_metadata(normalized_path, metadata)
        logger.info(f"Marked {normalized_path} as verified by {verified_by}")

    def unmark_verified(self, playbook_path: str):
        """
        Unmark playbook as verified

        Args:
            playbook_path: Relative path from playbooks directory
        """
        normalized_path = self._normalize_path(playbook_path)
        metadata = self.get_metadata(normalized_path)
        metadata.unmark_verified()
        self.update_metadata(normalized_path, metadata)
        logger.info(f"Unmarked {normalized_path} as verified")

    def set_enabled(self, playbook_path: str, enabled: bool):
        """
        Set playbook enabled/disabled state

        Args:
            playbook_path: Relative path from playbooks directory
            enabled: True to enable, False to disable
        """
        normalized_path = self._normalize_path(playbook_path)
        metadata = self.get_metadata(normalized_path)
        metadata.enabled = enabled
        self.update_metadata(normalized_path, metadata)
        logger.info(f"Set {normalized_path} enabled={enabled}")

    def delete_metadata(self, playbook_path: str) -> bool:
        """
        Delete metadata for a playbook

        Args:
            playbook_path: Relative path from playbooks directory

        Returns:
            True if metadata was deleted, False if not found
        """
        normalized_path = self._normalize_path(playbook_path)
        if normalized_path in self._metadata:
            del self._metadata[normalized_path]
            self._save()
            logger.info(f"Deleted metadata for {normalized_path}")
            return True
        return False

    def list_all(self) -> dict[str, PlaybookMetadata]:
        """
        Get all playbook metadata

        Returns:
            Dictionary mapping playbook paths to metadata
        """
        return self._metadata.copy()

    def reset_all(self):
        """
        Reset all playbook metadata (clears all verification states, etc.)

        This is useful for troubleshooting path-related issues.
        """
        self._metadata = {}
        self._save()
        logger.info("Reset all playbook metadata")

    def mark_as_built_in(self, playbook_path: str):
        """
        Mark playbook as built-in (shipped with toolkit)

        Args:
            playbook_path: Relative path from playbooks directory
        """
        metadata = self.get_metadata(playbook_path)
        metadata.mark_as_built_in()
        self.update_metadata(playbook_path, metadata)
        logger.info(f"Marked {playbook_path} as built-in")

    def mark_as_user_created(self, playbook_path: str):
        """
        Mark playbook as user-created

        Args:
            playbook_path: Relative path from playbooks directory
        """
        metadata = self.get_metadata(playbook_path)
        metadata.mark_as_user_created()
        self.update_metadata(playbook_path, metadata)
        logger.info(f"Marked {playbook_path} as user-created")

    def mark_as_duplicated(self, playbook_path: str, source_path: str):
        """
        Mark playbook as duplicated from another playbook

        Args:
            playbook_path: Relative path from playbooks directory
            source_path: Path of source playbook that was duplicated
        """
        metadata = self.get_metadata(playbook_path)
        metadata.mark_as_duplicated(source_path)
        self.update_metadata(playbook_path, metadata)
        logger.info(f"Marked {playbook_path} as duplicated from {source_path}")

    def mark_as_imported(self, playbook_path: str):
        """
        Mark playbook as imported from JSON export

        Args:
            playbook_path: Relative path from playbooks directory
        """
        metadata = self.get_metadata(playbook_path)
        metadata.origin = "imported"
        metadata.created_at = datetime.now().isoformat()
        self.update_metadata(playbook_path, metadata)
        logger.info(f"Marked {playbook_path} as imported")

    def mark_as_library_installed(self, playbook_path: str, *, verified: bool = False):
        """
        Mark playbook as installed from the GitHub playbook library.

        This prevents auto-sync from overwriting library-installed playbooks
        with older bundled versions (auto-sync only fires when origin is
        "built-in" or "unknown").

        Args:
            playbook_path: Relative path from playbooks directory
            verified: Whether the playbook is verified in the library index
        """
        metadata = self.get_metadata(playbook_path)
        metadata.origin = "library"
        metadata.created_at = datetime.now().isoformat()
        if verified:
            metadata.verified = True
            metadata.verified_at = datetime.now().isoformat()
            metadata.verified_by = "library"
        self.update_metadata(playbook_path, metadata)
        logger.info(f"Marked {playbook_path} as library-installed (verified={verified})")

    def auto_detect_built_ins(self, playbooks_dir: Path):
        """
        Auto-detect and mark built-in playbooks

        Built-in playbooks are those in:
        - playbooks/gateway/
        - playbooks/perspective/
        - playbooks/designer/
        - playbooks/examples/

        But NOT in user-created directories

        Args:
            playbooks_dir: Path to playbooks directory
        """
        built_in_dirs = ["gateway", "perspective", "designer", "examples"]

        for dir_name in built_in_dirs:
            dir_path = playbooks_dir / dir_name
            if not dir_path.exists():
                continue

            # Find all YAML files in this directory
            for yaml_file in dir_path.rglob("*.yaml"):
                try:
                    relative_path = yaml_file.relative_to(playbooks_dir)
                    relative_path_str = str(relative_path)

                    # Get metadata
                    metadata = self.get_metadata(relative_path_str)

                    # Only mark as built-in if origin is unknown
                    if metadata.origin == "unknown":
                        metadata.mark_as_built_in()
                        self.update_metadata(relative_path_str, metadata)
                        logger.debug(f"Auto-marked {relative_path_str} as built-in")

                except Exception as e:
                    logger.warning(f"Error processing {yaml_file}: {e}")

        logger.info("Completed auto-detection of built-in playbooks")

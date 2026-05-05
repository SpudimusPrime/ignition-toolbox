"""
Playbook submitter - Submit playbooks to the GitHub library

Uses GitHub Git Trees/Commits API to create commits that add playbooks
to the central repository.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from ignition_toolkit.core.paths import get_user_data_dir
from ignition_toolkit.playbook.registry import DEFAULT_REPO

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
SETTINGS_FILE = "github_settings.json"


def _get_settings_path() -> Path:
    """Get path to GitHub settings file."""
    return get_user_data_dir() / SETTINGS_FILE


def get_github_token() -> str | None:
    """Read GitHub PAT from settings file."""
    path = _get_settings_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("github_token")
    except Exception:
        return None


def save_github_token(token: str) -> None:
    """Save GitHub PAT to settings file."""
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing settings if any
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            pass

    data["github_token"] = token
    path.write_text(json.dumps(data, indent=2))
    logger.info("GitHub token saved")


def delete_github_token() -> None:
    """Remove GitHub PAT from settings file."""
    path = _get_settings_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        data.pop("github_token", None)
        path.write_text(json.dumps(data, indent=2))
        logger.info("GitHub token removed")
    except Exception:
        pass


def get_token_preview() -> str | None:
    """Get a masked preview of the stored token (first 4 + last 4 chars)."""
    token = get_github_token()
    if not token:
        return None
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


# ── Private repository ────────────────────────────────────────────────────────

def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def _parse_repo_slug(repo_url: str) -> str:
    """Normalise any GitHub URL or slug to 'owner/repo'."""
    url = repo_url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    if url.endswith(".git"):
        url = url[:-4]
    return url


def save_private_repo_settings(token: str, repo_url: str, folder: str = "") -> None:
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            pass
    data["private_repo_token"] = token.strip()
    data["private_repo_url"] = repo_url.strip()
    data["private_repo_folder"] = folder.strip().strip("/")
    path.write_text(json.dumps(data, indent=2))
    logger.info("Private repo settings saved")


def get_private_repo_settings() -> dict[str, str] | None:
    path = _get_settings_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        token = data.get("private_repo_token")
        repo_url = data.get("private_repo_url")
        if not token or not repo_url:
            return None
        return {
            "token": token,
            "repo_url": repo_url,
            "folder": data.get("private_repo_folder", ""),
        }
    except Exception:
        return None


def delete_private_repo_settings() -> None:
    path = _get_settings_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        data.pop("private_repo_token", None)
        data.pop("private_repo_url", None)
        data.pop("private_repo_folder", None)
        path.write_text(json.dumps(data, indent=2))
        logger.info("Private repo settings removed")
    except Exception:
        pass


def get_private_repo_preview() -> dict[str, Any]:
    settings = get_private_repo_settings()
    if not settings:
        return {"configured": False}
    return {
        "configured": True,
        "repo_url": settings["repo_url"],
        "folder": settings["folder"],
        "token_preview": _mask_token(settings["token"]),
    }


async def submit_to_private_repo(
    yaml_content: str,
    playbook_path: str,
    commit_message: str = "",
) -> dict[str, Any]:
    """
    Commit a playbook YAML to the user's private GitHub repository.

    Uses the Contents API (PUT /repos/{owner}/{repo}/contents/{path}) which
    handles both create and update in one call.  The file's current SHA is
    fetched first so updates don't conflict with existing content.
    """
    settings = get_private_repo_settings()
    if not settings:
        raise ValueError(
            "Private repository not configured. "
            "Add your token and repo URL in Settings → Integrations."
        )

    repo = _parse_repo_slug(settings["repo_url"])
    token = settings["token"]
    folder = settings["folder"]

    # Build target path inside the repo
    clean_path = playbook_path.replace("\\", "/")
    file_path = f"{folder}/{clean_path}" if folder else clean_path

    if not commit_message:
        name = clean_path.split("/")[-1].replace(".yaml", "")
        commit_message = f"Update playbook: {name}"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    import base64

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Validate repo access and get default branch
        repo_resp = await client.get(f"{GITHUB_API}/repos/{repo}", headers=headers)
        if repo_resp.status_code == 401:
            raise ValueError("Authentication failed — check your GitHub PAT.")
        if repo_resp.status_code == 404:
            raise ValueError(
                f"Repository '{repo}' not found. "
                "Check the URL and that your token has repo access."
            )
        repo_resp.raise_for_status()
        default_branch = repo_resp.json().get("default_branch", "main")

        # Check if the file already exists so we can pass its SHA for updates
        existing_sha: str | None = None
        existing_resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
            headers=headers,
            params={"ref": default_branch},
        )
        if existing_resp.status_code == 200:
            existing_sha = existing_resp.json().get("sha")

        # Commit the file
        payload: dict[str, Any] = {
            "message": commit_message,
            "content": base64.b64encode(yaml_content.encode()).decode(),
            "branch": default_branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        put_resp = await client.put(
            f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
            headers=headers,
            json=payload,
        )
        put_resp.raise_for_status()

        result = put_resp.json()
        commit_sha = result["commit"]["sha"]
        commit_url = result["commit"]["html_url"]
        action = "updated" if existing_sha else "created"

        logger.info(f"Playbook {action} in private repo: {commit_url}")
        return {
            "commit_url": commit_url,
            "sha": commit_sha,
            "file_path": file_path,
            "action": action,
            "message": f"'{clean_path}' {action} in {repo}",
        }


async def submit_playbook(
    yaml_content: str,
    playbook_path: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Submit a playbook to the GitHub library via Git Trees/Commits API.

    Creates a single commit with:
    - The YAML file at library/{domain}/{filename}.yaml
    - Updated playbooks-index.json with new entry

    Args:
        yaml_content: The YAML content of the playbook
        playbook_path: The playbook path (e.g., "gateway/my_playbook.yaml")
        metadata: Dict with keys: name, version, description, domain, author, tags, group, release_notes

    Returns:
        Dict with commit_url, sha, message
    """
    token = get_github_token()
    if not token:
        raise ValueError("GitHub token not configured. Please set your GitHub PAT in Settings > Integrations.")

    domain = metadata.get("domain", "gateway")
    filename = playbook_path.split("/")[-1]
    library_path = f"library/{domain}/{filename}"

    # Calculate checksum
    checksum = hashlib.sha256(yaml_content.encode()).hexdigest()

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Get the default branch ref
        ref_resp = await client.get(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/ref/heads/main",
            headers=headers,
        )
        if ref_resp.status_code == 404:
            raise ValueError(f"Repository {DEFAULT_REPO} not found or no access. Check your token permissions.")
        ref_resp.raise_for_status()
        base_sha = ref_resp.json()["object"]["sha"]

        # 2. Get the base tree
        commit_resp = await client.get(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/commits/{base_sha}",
            headers=headers,
        )
        commit_resp.raise_for_status()
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        # 3. Try to get existing playbooks-index.json
        index_content: dict[str, Any] = {"playbooks": []}
        index_resp = await client.get(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/contents/playbooks-index.json",
            headers=headers,
        )
        if index_resp.status_code == 200:
            import base64
            content_b64 = index_resp.json()["content"]
            index_content = json.loads(base64.b64decode(content_b64))

        # 4. Update index with new entry (or update existing)
        download_url = f"https://raw.githubusercontent.com/{DEFAULT_REPO}/main/{library_path}"
        new_entry = {
            "playbook_path": f"{domain}/{filename.replace('.yaml', '')}",
            "version": metadata.get("version", "1.0"),
            "domain": domain,
            "description": metadata.get("description", ""),
            "author": metadata.get("author", "Community"),
            "tags": metadata.get("tags", []),
            "group": metadata.get("group", ""),
            "release_notes": metadata.get("release_notes"),
            "checksum": checksum,
            "download_url": download_url,
            "verified": False,
            "verified_by": None,
            "size_bytes": len(yaml_content.encode()),
        }

        # Remove existing entry for same path if it exists
        existing_playbooks = [
            p for p in index_content.get("playbooks", [])
            if p.get("playbook_path") != new_entry["playbook_path"]
        ]
        existing_playbooks.append(new_entry)
        index_content["playbooks"] = existing_playbooks

        updated_index = json.dumps(index_content, indent=2)

        # 5. Create blobs for both files
        yaml_blob_resp = await client.post(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/blobs",
            headers=headers,
            json={"content": yaml_content, "encoding": "utf-8"},
        )
        yaml_blob_resp.raise_for_status()
        yaml_blob_sha = yaml_blob_resp.json()["sha"]

        index_blob_resp = await client.post(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/blobs",
            headers=headers,
            json={"content": updated_index, "encoding": "utf-8"},
        )
        index_blob_resp.raise_for_status()
        index_blob_sha = index_blob_resp.json()["sha"]

        # 6. Create tree with both files
        tree_resp = await client.post(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/trees",
            headers=headers,
            json={
                "base_tree": base_tree_sha,
                "tree": [
                    {
                        "path": library_path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": yaml_blob_sha,
                    },
                    {
                        "path": "playbooks-index.json",
                        "mode": "100644",
                        "type": "blob",
                        "sha": index_blob_sha,
                    },
                ],
            },
        )
        tree_resp.raise_for_status()
        new_tree_sha = tree_resp.json()["sha"]

        # 7. Create commit
        name = metadata.get("name", filename)
        commit_message = f"Add playbook: {name}\n\nSubmitted via Ignition Toolbox"
        if metadata.get("release_notes"):
            commit_message += f"\n\n{metadata['release_notes']}"

        new_commit_resp = await client.post(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/commits",
            headers=headers,
            json={
                "message": commit_message,
                "tree": new_tree_sha,
                "parents": [base_sha],
            },
        )
        new_commit_resp.raise_for_status()
        new_commit_sha = new_commit_resp.json()["sha"]

        # 8. Update ref
        update_ref_resp = await client.patch(
            f"{GITHUB_API}/repos/{DEFAULT_REPO}/git/refs/heads/main",
            headers=headers,
            json={"sha": new_commit_sha},
        )
        update_ref_resp.raise_for_status()

        commit_url = f"https://github.com/{DEFAULT_REPO}/commit/{new_commit_sha}"
        logger.info(f"Playbook submitted: {commit_url}")

        return {
            "commit_url": commit_url,
            "sha": new_commit_sha,
            "message": f"Playbook '{name}' submitted successfully",
            "library_path": library_path,
        }

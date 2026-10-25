import shutil
import tempfile
import zipfile

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import requests

from memos.embedders.base import BaseEmbedder
from memos.log import get_logger
from memos.mem_reader.read_skill_memory.process_skill_memory import (
    create_skill_memory_item,
)
from memos.mem_reader.read_skill_memory.skill_package import parse_skill_package
from memos.memories.textual.item import TextualMemoryItem
from memos.utils import timed


logger = get_logger(__name__)


def _extract_zip_url_from_items(items: list[TextualMemoryItem]) -> str | None:
    """
    Extract the zip download URL from fast-stage memory items.

    FileContentParser.parse_fast stores the URL in source.file_info["file_data"].
    Each upload-skill request contains exactly one zip URL.
    """
    for item in items:
        for source in getattr(item.metadata, "sources", None) or []:
            file_info = getattr(source, "file_info", None)
            if not isinstance(file_info, dict):
                continue
            file_data = file_info.get("file_data", "")
            if isinstance(file_data, str) and file_data.startswith(("http://", "https://")):
                url_path = urlparse(file_data).path
                if url_path.lower().endswith(".zip"):
                    return file_data
    return None


def _extract_file_ids_from_items(items: list[TextualMemoryItem]) -> list[str]:
    """Extract uploaded file ids from fast-stage memory metadata and sources."""
    file_ids: list[str] = []

    def _append_file_id(file_id: Any) -> None:
        if isinstance(file_id, str) and file_id and file_id not in file_ids:
            file_ids.append(file_id)

    for item in items:
        metadata = getattr(item, "metadata", None)
        metadata_file_ids = getattr(metadata, "file_ids", None) if metadata else None
        if isinstance(metadata_file_ids, list):
            for file_id in metadata_file_ids:
                _append_file_id(file_id)

        for source in getattr(metadata, "sources", None) or []:
            file_info = getattr(source, "file_info", None)
            if isinstance(file_info, dict):
                _append_file_id(file_info.get("file_id"))

    return file_ids


def _download_zip(url: str, tmp_dir: Path) -> Path:
    """Download a zip file to a local temporary directory."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        raise ValueError(f"Failed to download zip from {url}: {e}") from e

    zip_path = tmp_dir / f"{uuid4()}.zip"
    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Downloaded file is not a valid zip: {url}")

    return zip_path


def _extract_and_parse_skill_zip(zip_path: Path, filename: str | None = None) -> dict[str, Any]:
    """Parse a downloaded skill zip into a skill_memory dict (full text, no truncation)."""
    return parse_skill_package(zip_path.read_bytes(), filename or zip_path.name)


@timed
def process_upload_skill_memory(
    fast_memory_items: list[TextualMemoryItem],
    info: dict[str, Any],
    embedder: BaseEmbedder | None = None,
    oss_config: dict[str, Any] | None = None,
    skills_dir_config: dict[str, Any] | None = None,
    **kwargs,
) -> list[TextualMemoryItem]:
    """
    Process a user-uploaded skill zip, parse it, and build a SkillMemory node.

    The zip URL is taken from the fast-stage ``TextualMemoryItem`` sources
    (``source.file_info["file_data"]``), consistent with both sync-fine and
    async-transfer paths.
    """
    zip_url = _extract_zip_url_from_items(fast_memory_items)
    if not zip_url:
        logger.warning("[UPLOAD_SKILL] No zip URL found in fast_memory_items")
        return []
    file_ids = _extract_file_ids_from_items(fast_memory_items)

    tmp_dir = Path(tempfile.mkdtemp(prefix="upload_skill_"))
    try:
        zip_path = _download_zip(zip_url, tmp_dir)
    except Exception as e:
        logger.warning("[UPLOAD_SKILL] Failed to download zip: %s", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return []

    try:
        skill_memory = _extract_and_parse_skill_zip(zip_path, Path(urlparse(zip_url).path).name)
    except ValueError as e:
        logger.warning("[UPLOAD_SKILL] Invalid skill zip: %s", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return []
    except Exception as e:
        logger.error("[UPLOAD_SKILL] Failed to parse skill zip: %s", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return []

    skill_memory["url"] = zip_url
    skill_memory["skill_source"] = "user_upload"

    try:
        skill_memory_item = create_skill_memory_item(skill_memory, info, embedder, **kwargs)
        if file_ids:
            skill_memory_item.metadata.file_ids = file_ids
            metadata_info = dict(skill_memory_item.metadata.info or {})
            metadata_info.setdefault("file_id", file_ids[0])
            skill_memory_item.metadata.info = metadata_info
    except Exception as e:
        logger.error("[UPLOAD_SKILL] Failed to create skill memory item: %s", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return []

    # Cleanup temp files
    shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info(
        "[UPLOAD_SKILL] Successfully created SkillMemory from uploaded zip: name=%s, id=%s",
        skill_memory.get("name"),
        skill_memory_item.id,
    )
    return [skill_memory_item]

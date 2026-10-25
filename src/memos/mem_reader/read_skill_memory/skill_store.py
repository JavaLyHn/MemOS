"""File storage for skill zips: per-user layout, atomic publish, guarded deletes.

LOCAL layout: ``<root>/<user_dir>/<slug>-<uid8>.zip`` where ``root`` is the directory served
at ``/download`` (``FILE_LOCAL_PATH/skills``) and ``user_dir`` is a hash of the user id, so users
never share a path and a user-controlled name can never leave the root. Every write gets a fresh
``uid8``, so an update never overwrites the file a live node still points to.
"""

import hashlib
import os
import re
import shutil
import sys
import threading
import uuid

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from memos.dependency import require_python_package
from memos.log import get_logger


logger = get_logger(__name__)

SLUG_MAX_CHARS = 48
_warned_unserved_root = False


def storage_backend() -> str:
    """Skill file storage backend from ``SKILLS_REPO_BACKEND``: OSS or LOCAL (default)."""
    raw = os.getenv("SKILLS_REPO_BACKEND")
    if raw is None or not raw.strip():
        return "LOCAL"
    backend = raw.strip().upper()
    if backend in {"OSS", "LOCAL"}:
        return backend
    logger.warning("Environment variable [SKILLS_REPO_BACKEND] is invalid, using LOCAL")
    return "LOCAL"


def skills_dir_config_from_env() -> dict[str, str]:
    """Same keys and defaults as the ``skills_dir_config`` built in ``api/config.py``."""
    return {
        "skills_oss_dir": os.getenv("SKILLS_OSS_DIR", "skill_memory/"),
        "skills_local_tmp_dir": os.getenv("SKILLS_LOCAL_TMP_DIR", "/tmp/skill_memory/"),
        "skills_local_dir": os.getenv("SKILLS_LOCAL_DIR", "/tmp/upload_skill_memory/"),
    }


def user_dir_name(user_id: str) -> str:
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16]


def skill_slug(name: str) -> str:
    slug = re.sub(r"\s+", "_", str(name or "").strip().lower())
    slug = re.sub(r"[^a-z0-9._-]", "_", slug)
    slug = re.sub(r"\.{2,}", ".", slug)
    slug = re.sub(r"_{2,}", "_", slug).strip("._-")
    slug = slug[:SLUG_MAX_CHARS].strip("._-")
    return slug or "skill"


def unique_zip_stem(name: str) -> str:
    return f"{skill_slug(name)}-{uuid.uuid4().hex[:8]}"


def unique_zip_name(name: str) -> str:
    return f"{unique_zip_stem(name)}.zip"


def local_skill_layout(skills_dir_config: dict[str, Any]) -> tuple[Path, str]:
    """Return (directory skills are written to, URL path prefix that serves it)."""
    global _warned_unserved_root
    served = os.getenv("FILE_LOCAL_PATH")
    if served:
        return Path(served) / "skills", "/download/skills"
    if not _warned_unserved_root:
        _warned_unserved_root = True
        logger.warning(
            "[SKILL_STORE] FILE_LOCAL_PATH is not set: skills are written to skills_local_dir "
            "but /download does not serve that directory, so the download URL will 404"
        )
    return Path(
        skills_dir_config.get("skills_local_dir") or "/tmp/upload_skill_memory/"
    ), "/download"


def download_base_url() -> str:
    configured = os.getenv("SKILLS_DOWNLOAD_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    args = sys.argv
    port = (
        args[args.index("--port") + 1]
        if "--port" in args and args.index("--port") + 1 < len(args)
        else "8000"
    )
    return f"http://localhost:{port}"


def publish_local_skill(zip_path: Path, user_id: str, skills_dir_config: dict[str, Any]) -> str:
    """Copy ``zip_path`` into the user's directory atomically and return its download URL."""
    root, prefix = local_skill_layout(skills_dir_config)
    udir = user_dir_name(user_id)
    target_dir = root / udir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / zip_path.name
    staging = target_dir / f".{zip_path.name}.{uuid.uuid4().hex[:8]}.part"
    try:
        shutil.copyfile(zip_path, staging)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    return f"{download_base_url()}{prefix}/{udir}/{zip_path.name}"


def local_path_for_url(url: str, user_id: str, skills_dir_config: dict[str, Any]) -> Path | None:
    """Map a download URL back to its file, only if it is a zip in this user's own directory."""
    if not url:
        return None
    root, prefix = local_skill_layout(skills_dir_config)
    path = urlparse(url).path
    if not path.startswith(prefix + "/"):
        return None
    segments = path[len(prefix) + 1 :].split("/")
    if len(segments) != 2:
        return None
    udir, filename = segments
    if udir != user_dir_name(user_id):
        return None
    if not filename.endswith(".zip") or filename.startswith(".") or "\\" in filename:
        return None
    return root / udir / filename


def delete_local_skill_url(url: str, user_id: str, skills_dir_config: dict[str, Any]) -> bool:
    target = local_path_for_url(url, user_id, skills_dir_config)
    if target is None:
        logger.info("[SKILL_STORE] not deleting %r: not a skill file owned by this user", url)
        return False
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.warning("[SKILL_STORE] failed to delete %s: %s", target, e)
        return False
    return True


@require_python_package(
    import_name="alibabacloud_oss_v2",
    install_command="pip install alibabacloud-oss-v2",
)
def upload_oss_skill(skills_oss_dir: str, zip_path: Path, client: Any, user_id: str) -> str:
    import alibabacloud_oss_v2 as oss

    key = oss_key(skills_oss_dir, user_id, zip_path.name)
    result = client.put_object_from_file(
        request=oss.PutObjectRequest(bucket=os.getenv("OSS_BUCKET_NAME"), key=key),
        filepath=str(zip_path),
    )
    if result.status_code != 200:
        logger.warning("[SKILL_STORE] Failed to upload skill to OSS")
        return ""
    endpoint = os.getenv("OSS_ENDPOINT", "").replace("https://", "").replace("http://", "")
    return f"https://{os.getenv('OSS_BUCKET_NAME')}.{endpoint}/{key}"


def publish_skill(
    zip_path: Path,
    user_id: str,
    *,
    backend: str,
    skills_dir_config: dict[str, Any],
    oss_client: Any = None,
) -> str:
    """Publish a skill zip to the configured backend and return its download URL ("" on failure)."""
    if backend == "OSS":
        return upload_oss_skill(
            skills_dir_config.get("skills_oss_dir", ""), zip_path, oss_client, user_id
        )
    return publish_local_skill(zip_path, user_id, skills_dir_config)


def safe_user_segment(user_id: str) -> str:
    uid = str(user_id)
    if (
        "/" in uid
        or "\\" in uid
        or uid in {"", ".", ".."}
        or not uid.isprintable()
        or len(uid) > 256
    ):
        return user_dir_name(uid)
    return uid


def oss_key(skills_oss_dir: str, user_id: str, filename: str) -> str:
    return (
        PurePosixPath(str(skills_oss_dir or "")) / safe_user_segment(user_id) / filename
    ).as_posix()


def oss_key_for_url(url: str, skills_oss_dir: str, user_id: str) -> str | None:
    if not url:
        return None
    key = PurePosixPath(unquote(urlparse(url).path).lstrip("/"))
    expected = PurePosixPath(oss_key(skills_oss_dir, user_id, "x.zip"))
    if key.parent != expected.parent or key.suffix != ".zip" or key.name in {"", ".zip"}:
        return None
    return key.as_posix()


def delete_skill_by_url(
    url: str,
    user_id: str,
    *,
    backend: str,
    skills_dir_config: dict[str, Any],
    oss_client: Any = None,
) -> bool:
    """Delete the skill file behind ``url`` if (and only if) it belongs to ``user_id``."""
    if backend == "OSS":
        key = oss_key_for_url(url, skills_dir_config.get("skills_oss_dir", ""), user_id)
        if key is None or oss_client is None:
            logger.info("[SKILL_STORE] not deleting %r from OSS", url)
            return False
        import alibabacloud_oss_v2 as oss

        oss_client.delete_object(
            oss.DeleteObjectRequest(bucket=os.getenv("OSS_BUCKET_NAME"), key=key)
        )
        return True
    return delete_local_skill_url(url, user_id, skills_dir_config)


_PENDING_LIMIT = 256
_pending: OrderedDict[tuple[str, str], tuple[Callable[[], None], Callable[[], None]]] = (
    OrderedDict()
)
_pending_lock = threading.Lock()


def defer_file_cleanup(
    item_id: str, url: str, *, on_stored: Callable[[], None], on_lost: Callable[[], None]
) -> None:
    """Hold back the file cleanup of a skill item until its graph write has been attempted.

    ``on_stored`` runs when the node ends up pointing at ``url`` (the replaced zip can go),
    ``on_lost`` when it does not (the zip just uploaded is the orphan). The graph writers swallow
    their own errors, so ``settle_file_cleanup`` reads the node back instead of trusting the call.
    Entries never settled age out, which only ever leaks a file and never deletes one.
    """
    with _pending_lock:
        _pending[(item_id, url)] = (on_stored, on_lost)
        while len(_pending) > _PENDING_LIMIT:
            _pending.popitem(last=False)


def settle_file_cleanup(graph: Any, items: list[Any], user_name: str | None = None) -> None:
    """Run the deferred cleanup of every skill item in ``items`` once its write was attempted."""
    for item in items:
        metadata = getattr(item, "metadata", None)
        if getattr(metadata, "memory_type", None) != "SkillMemory":
            continue
        url = getattr(metadata, "url", None) or ""
        with _pending_lock:
            hooks = _pending.pop((item.id, url), None)
        if hooks is None:
            continue
        try:
            node = graph.get_node(item.id, user_name=user_name)
        except Exception as e:  # noqa: BLE001 - unsure what is stored: keep every file
            logger.warning("[SKILL_STORE] could not read back %s: %s", item.id, e)
            continue
        stored_url = ((node or {}).get("metadata") or {}).get("url")
        on_stored, on_lost = hooks
        try:
            (on_stored if stored_url == url else on_lost)()
        except Exception as e:  # noqa: BLE001 - the node is settled; a stray file is only a leak
            logger.warning("[SKILL_STORE] file cleanup for %s failed: %s", item.id, e)

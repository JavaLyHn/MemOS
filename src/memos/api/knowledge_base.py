"""Knowledge base MVP: entities, PVC file storage, CRUD and a pluggable ingest hook.

Scope (deliberate):

* knowledge base + file entities, tenant scoped;
* file bytes on local PVC (``KB_STORAGE_DIR``);
* create / list / get / delete KB, upload / list / delete / download files;
* an ``IngestPipeline`` interface with a ``NoopIngestor`` implementation.

Parsing, chunking, dual (raw + processed) memory generation and KB recall are
follow-up work. ``search`` accepts ``knowledgebase_ids`` but returns no KB hits
while ``KB_RECALL_ENABLED=false`` so the contract does not silently change.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import io
import os
import re
import uuid
import zipfile
import zlib

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol

import yaml

from memos.log import get_logger
from memos.mem_reader.read_skill_memory.skill_package import (
    SKILL_MANIFEST,
    SKILL_MANIFEST_MAX_BYTES,
    SKILL_ZIP_MAX_ENTRIES,
    SKILL_ZIP_MAX_FILE_BYTES,
    SKILL_ZIP_MAX_UNPACKED_BYTES,
)


if TYPE_CHECKING:
    from memos.api.cloud_store import MetadataStore


logger = get_logger(__name__)

KB_KIND = "knowledgebase"
KB_FILE_KIND = "knowledgebase_file"
DEFAULT_KB_STORAGE_DIR = "/data/memos/kb"
ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt", "json", "md", "xml"}

SKILL_FILE_TYPE = "skill"
FILE_TYPES = frozenset({"document", SKILL_FILE_TYPE})
BINARY_MAGIC = {"zip": b"PK", "docx": b"PK", "pdf": b"%PDF", "doc": b"\xd0\xcf\x11\xe0"}
SKILL_ZIP_MAX_BYTES = 20 * 1024 * 1024
SKILL_NAME_MAX_CHARS = 64
SKILL_DESCRIPTION_MAX_CHARS = 1024


def kb_recall_enabled() -> bool:
    raw = os.getenv("KB_RECALL_ENABLED", "false")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Environment variable [%s]=%r is not an integer, using %d", name, raw, default
        )
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _safe_name(name: str) -> str:
    """Keep only the base name; never let callers escape the storage root."""
    base = os.path.basename(str(name or "")).replace("\x00", "").strip()
    return base or "unnamed"


def _extension(name: str) -> str:
    return Path(_safe_name(name)).suffix.lower().lstrip(".")


def _tenant_dir(tenant: str) -> str:
    return hashlib.sha256((tenant or "default").encode("utf-8")).hexdigest()[:16]


class IngestPipeline(Protocol):
    """Pluggable document processing hook (parse / chunk / embed / index)."""

    def ingest(
        self,
        *,
        user_name: str,
        knowledgebase: dict[str, Any],
        file: dict[str, Any],
        content: bytes,
    ) -> dict[str, Any]:
        """Process one uploaded file and return a status document."""
        ...


class NoopIngestor:
    """MVP ingestor: keeps the bytes only, produces no recallable chunks."""

    def ingest(
        self,
        *,
        user_name: str,
        knowledgebase: dict[str, Any],
        file: dict[str, Any],
        content: bytes,
    ) -> dict[str, Any]:
        return {
            "status": "stored",
            "chunks": 0,
            "detail": "KB parsing/chunking/embedding is not enabled in this build",
        }


class SkillSink(Protocol):
    """Turns an uploaded skill file into a recallable SkillMemory, and removes it again."""

    def add_skill(
        self,
        *,
        user_name: str,
        owner_user_id: str | None,
        file_id: str,
        name: str,
        content: bytes,
    ) -> dict[str, Any]:
        """Create the SkillMemory for one validated upload; return fields to record on the file."""
        ...

    def remove_skill(
        self, *, user_name: str, owner_user_id: str | None, file: dict[str, Any]
    ) -> None:
        """Delete the SkillMemory and skill file created for ``file``. Raises if the node stays."""
        ...


def build_ingestor() -> IngestPipeline:
    backend = os.getenv("MEMOS_KB_INGESTOR", "noop").strip().lower()
    if backend in ("", "noop", "none"):
        return NoopIngestor()
    logger.warning("Unknown MEMOS_KB_INGESTOR=%r, falling back to noop", backend)
    return NoopIngestor()


@dataclass
class KnowledgeBaseService:
    """Tenant-scoped knowledge base management."""

    store: MetadataStore
    storage_dir: Path
    ingestor: IngestPipeline
    skill_sink: SkillSink | None = None

    @classmethod
    def from_env(
        cls, store: MetadataStore, skill_sink: SkillSink | None = None
    ) -> KnowledgeBaseService:
        storage_dir = Path(os.getenv("KB_STORAGE_DIR", DEFAULT_KB_STORAGE_DIR))
        storage_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            store=store,
            storage_dir=storage_dir,
            ingestor=build_ingestor(),
            skill_sink=skill_sink,
        )

    # ── knowledge bases ──────────────────────────────────────────────────────

    def create(
        self,
        *,
        user_name: str,
        name: str,
        description: str | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("knowledgebase_name is required")
        now = _utc_now()
        document = {
            "entity_id": _new_id("kb"),
            "user_name": user_name,
            "owner_user_id": owner_user_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "file_count": 0,
            "total_size": 0,
        }
        self.store.put(KB_KIND, document)
        return document

    def list(self, *, user_name: str, page: int | None = None, page_size: int | None = None):
        documents = self.store.list(KB_KIND, user_name=user_name)
        return _paginate(documents, page, page_size)

    def get(self, *, user_name: str, knowledgebase_id: str) -> dict[str, Any] | None:
        return self._owned_kb(user_name, knowledgebase_id)

    def update(
        self,
        *,
        user_name: str,
        knowledgebase_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any] | None:
        kb = self._owned_kb(user_name, knowledgebase_id)
        if kb is None:
            return None
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("knowledgebase_name is required")
            kb["name"] = name
        if description is not None:
            kb["description"] = description
        kb["updated_at"] = _utc_now()
        self.store.put(KB_KIND, kb)
        return kb

    def delete(self, *, user_name: str, knowledgebase_id: str) -> bool:
        kb = self._owned_kb(user_name, knowledgebase_id)
        if kb is None:
            return False
        for file_doc in self.store.list(KB_FILE_KIND, user_name=user_name):
            if file_doc.get("knowledgebase_id") == knowledgebase_id:
                self._remove_file(user_name, file_doc)
        self.store.delete(KB_KIND, knowledgebase_id)
        return True

    # ── files ────────────────────────────────────────────────────────────────

    def add_files(
        self,
        *,
        user_name: str,
        knowledgebase_id: str,
        files: list[dict[str, Any]],
        file_type: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Add files described as ``{name, content|base64|url|bytes}``."""
        kb = self._owned_kb(user_name, knowledgebase_id)
        if kb is None:
            raise ValueError(f"knowledgebase not found: {knowledgebase_id}")
        if not files:
            raise ValueError("at least one file is required")

        max_files = _env_int("KB_MAX_FILES_PER_UPLOAD", 20)
        if len(files) > max_files:
            raise ValueError(f"at most {max_files} files are allowed per upload")

        max_size_mb = _env_int("KB_MAX_FILE_SIZE_MB", 100)
        max_size = max_size_mb * 1024 * 1024
        max_pages = _env_int("KB_MAX_FILE_PAGES", 500)

        # Validate every file *before* writing any bytes, so one bad item in a
        # batch does not leave a half-imported knowledge base behind.
        prepared: list[tuple[str, bytes, str, Any, dict[str, str], str | None]] = []
        for item in files:
            kind = _item_file_type(item, file_type)
            is_skill = kind == SKILL_FILE_TYPE
            allowed = ALLOWED_EXTENSIONS | {"zip"} if is_skill else ALLOWED_EXTENSIONS
            name = _file_name(item)
            ext = _extension(name)
            content = _file_bytes(item, max_size=max_size, magic=BINARY_MAGIC.get(ext))
            if ext not in allowed:
                raise ValueError(
                    f"unsupported file type {ext or '(none)'}; allowed: "
                    f"{', '.join(sorted(allowed))}"
                )
            if len(content) > max_size:
                raise ValueError(f"{name} exceeds the {max_size_mb} MB per-file limit")
            pages = item.get("pages")
            if pages is not None and int(pages) > max_pages:
                raise ValueError(f"{name} exceeds the {max_pages} page limit")
            skill = inspect_skill_upload(name, ext, content) if is_skill else {}
            prepared.append((name, content, ext, pages, skill, kind))

        added: list[dict[str, Any]] = []
        for item, (name, content, ext, pages, skill, kind) in zip(files, prepared, strict=True):
            is_skill = kind == SKILL_FILE_TYPE
            file_id = _new_id("file")
            now = _utc_now()
            storage_path = self._storage_path(user_name, knowledgebase_id, file_id, ext)
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(storage_path, content)

            document = {
                "entity_id": file_id,
                "user_name": user_name,
                "owner_user_id": owner_user_id,
                "knowledgebase_id": knowledgebase_id,
                "name": name,
                "ext": ext,
                "size": len(content),
                "pages": pages,
                "file_type": kind,
                "source_url": item.get("url") or item.get("source_url"),
                "storage_path": str(storage_path),
                "status": "stored",
                "created_at": now,
                "updated_at": now,
            }
            if skill:
                document["skill_name"] = skill["name"]
                document["skill_description"] = skill["description"]
            try:
                ingest_result = self.ingestor.ingest(
                    user_name=user_name,
                    knowledgebase=kb,
                    file=document,
                    content=content,
                )
                document.update(
                    {
                        "status": ingest_result.get("status", "stored"),
                        "chunks": ingest_result.get("chunks", 0),
                    }
                )
                if is_skill and self.skill_sink is not None:
                    document.update(
                        self.skill_sink.add_skill(
                            user_name=user_name,
                            owner_user_id=owner_user_id,
                            file_id=file_id,
                            name=name,
                            content=content,
                        )
                    )
            except Exception as e:
                logger.warning("KB ingest failed for %s: %s", file_id, e, exc_info=True)
                document["status"] = "failed"
                document["error"] = str(e)

            self.store.put(KB_FILE_KIND, document)
            added.append(document)

        self._refresh_kb_stats(user_name, knowledgebase_id)
        return added

    def list_files(
        self,
        *,
        user_name: str,
        knowledgebase_id: str | None = None,
        file_ids: list[str] | None = None,
        file_type: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if knowledgebase_id is not None and self._owned_kb(user_name, knowledgebase_id) is None:
            raise ValueError(f"knowledgebase not found: {knowledgebase_id}")

        documents = self.store.list(KB_FILE_KIND, user_name=user_name)
        if knowledgebase_id is not None:
            documents = [
                doc for doc in documents if doc.get("knowledgebase_id") == knowledgebase_id
            ]
        if file_ids is not None:
            wanted = set(file_ids)
            documents = [doc for doc in documents if doc.get("entity_id") in wanted]
        if file_type is not None:
            documents = [doc for doc in documents if doc.get("file_type") == file_type]

        return _paginate(documents, page, page_size)

    def get_file(self, *, user_name: str, file_id: str) -> dict[str, Any] | None:
        document = self.store.get(KB_FILE_KIND, file_id)
        if document is None or document.get("user_name") != user_name:
            return None
        return document

    def read_file(self, *, user_name: str, file_id: str) -> tuple[bytes, dict[str, Any]] | None:
        document = self.get_file(user_name=user_name, file_id=file_id)
        if document is None:
            return None
        path = Path(document.get("storage_path") or "")
        try:
            resolved = path.resolve()
            root = self.storage_dir.resolve()
        except OSError:
            return None
        if root not in resolved.parents or not resolved.is_file():
            logger.warning("Refusing to read KB file outside storage root: %s", path)
            return None
        max_size_mb = _env_int("KB_MAX_FILE_SIZE_MB", 100)
        if resolved.stat().st_size > max_size_mb * 1024 * 1024:
            raise ValueError(f"file exceeds the {max_size_mb} MB download limit")
        return resolved.read_bytes(), document

    def delete_files(self, *, user_name: str, file_ids: list[str]) -> int:
        deleted = 0
        touched_kbs: set[str] = set()
        for file_id in file_ids:
            document = self.get_file(user_name=user_name, file_id=file_id)
            if document is None:
                continue
            if self._remove_file(user_name, document):
                deleted += 1
                touched_kbs.add(str(document.get("knowledgebase_id")))
        for kb_id in touched_kbs:
            self._refresh_kb_stats(user_name, kb_id)
        return deleted

    # ── internals ────────────────────────────────────────────────────────────

    def _owned_kb(self, user_name: str, knowledgebase_id: str) -> dict[str, Any] | None:
        document = self.store.get(KB_KIND, knowledgebase_id)
        if document is None or document.get("user_name") != user_name:
            return None
        return document

    def _storage_path(self, tenant: str, kb_id: str, file_id: str, ext: str) -> Path:
        suffix = f".{ext}" if ext else ""
        return self.storage_dir / _tenant_dir(tenant) / kb_id / f"{file_id}{suffix}"

    def _remove_file(self, user_name: str, document: dict[str, Any]) -> bool:
        if document.get("file_type") == SKILL_FILE_TYPE and self.skill_sink is not None:
            try:
                self.skill_sink.remove_skill(
                    user_name=user_name,
                    owner_user_id=document.get("owner_user_id"),
                    file=document,
                )
            except Exception as e:
                logger.warning(
                    "Keeping KB file %s: its SkillMemory could not be removed: %s",
                    document.get("entity_id"),
                    e,
                    exc_info=True,
                )
                return False
        path = Path(document.get("storage_path") or "")
        try:
            resolved = path.resolve()
            root = self.storage_dir.resolve()
            if resolved.exists() and root in resolved.parents:
                resolved.unlink()
        except OSError:
            logger.warning("Failed to remove KB file bytes: %s", path, exc_info=True)
        return self.store.delete(KB_FILE_KIND, document["entity_id"])

    def _refresh_kb_stats(self, user_name: str, knowledgebase_id: str) -> None:
        kb = self._owned_kb(user_name, knowledgebase_id)
        if kb is None:
            return
        files = [
            doc
            for doc in self.store.list(KB_FILE_KIND, user_name=user_name)
            if doc.get("knowledgebase_id") == knowledgebase_id
        ]
        kb["file_count"] = len(files)
        kb["total_size"] = sum(int(doc.get("size") or 0) for doc in files)
        kb["updated_at"] = _utc_now()
        self.store.put(KB_KIND, kb)


def _file_name(item: dict[str, Any]) -> str:
    """Resolve a display name, deriving the extension from a URL if needed."""
    name = _safe_name(item.get("name") or item.get("filename") or "")
    if name == "unnamed":
        source = str(item.get("url") or item.get("source_url") or "").strip()
        if source:
            from urllib.parse import urlparse

            name = _safe_name(os.path.basename(urlparse(source).path))
    if name == "unnamed":
        return name
    if not _extension(name):
        source = str(item.get("url") or item.get("source_url") or "").strip()
        if source:
            from urllib.parse import urlparse

            url_ext = Path(urlparse(source).path).suffix.lower().lstrip(".")
            if url_ext in ALLOWED_EXTENSIONS:
                name = f"{name}.{url_ext}"
    return name


def _atomic_write(path: Path, content: bytes) -> None:
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def inspect_skill_upload(name: str, ext: str, content: bytes) -> dict[str, str]:
    """Validate a skill upload and return its ``name`` / ``description``.

    A skill is either a ``.zip`` package or a standalone ``.md`` file. The bytes
    are only inspected, never extracted, so nothing in the archive can write
    outside the storage root. Limits follow the official cloud documentation.
    """
    if ext == "zip":
        manifest = _read_skill_zip(name, content)
    elif ext == "md":
        manifest = content
    else:
        raise ValueError(f"{name}: a skill upload must be a .zip package or a .md file")
    if len(manifest) > SKILL_MANIFEST_MAX_BYTES:
        raise ValueError(f"{name}: {SKILL_MANIFEST} exceeds {SKILL_MANIFEST_MAX_BYTES // 1024} KB")
    return _parse_skill_manifest(name, manifest)


def _zip_entry_parts(entry: str) -> tuple[str, ...]:
    normalized = entry.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in parts:
        raise ValueError(f"zip entry {entry!r} escapes the package root")
    return tuple(part for part in parts if part != ".")


def _read_skill_zip(name: str, content: bytes) -> bytes:
    if len(content) > SKILL_ZIP_MAX_BYTES:
        raise ValueError(
            f"{name} exceeds the {SKILL_ZIP_MAX_BYTES // (1024 * 1024)} MB skill limit"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        raise ValueError(f"{name} is not a valid zip archive") from e

    with archive:
        files: list[tuple[tuple[str, ...], zipfile.ZipInfo]] = []
        for info in archive.infolist():
            if info.filename.startswith("__MACOSX/"):
                continue
            parts = _zip_entry_parts(info.filename)
            if info.flag_bits & 0x1:
                raise ValueError(f"{name} contains encrypted entries")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"{name} contains a symbolic link: {info.filename!r}")
            if parts and not info.is_dir():
                files.append((parts, info))

        if len(files) > SKILL_ZIP_MAX_ENTRIES:
            raise ValueError(f"{name} has more than {SKILL_ZIP_MAX_ENTRIES} files")
        for parts, info in files:
            if info.file_size > SKILL_ZIP_MAX_FILE_BYTES:
                raise ValueError(
                    f"{name}: {'/'.join(parts)} is larger than the "
                    f"{SKILL_ZIP_MAX_FILE_BYTES // (1024 * 1024)} MB per-file limit"
                )
        if sum(info.file_size for _, info in files) > SKILL_ZIP_MAX_UNPACKED_BYTES:
            raise ValueError(f"{name} unpacks to more than the allowed size")

        manifest = next((info for parts, info in files if parts == (SKILL_MANIFEST,)), None)
        if manifest is None:
            raise ValueError(
                f"{name}: {SKILL_MANIFEST} must be at the first level of the package; "
                "zip the folder's contents directly, not the folder itself"
            )
        try:
            with archive.open(manifest) as handle:
                return handle.read(SKILL_MANIFEST_MAX_BYTES + 1)
        except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as e:
            raise ValueError(f"{name}: cannot read {SKILL_MANIFEST}: {e}") from e


def _parse_skill_manifest(name: str, raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError(f"{name}: {SKILL_MANIFEST} is not valid UTF-8") from e
    match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError(f"{name}: {SKILL_MANIFEST} must start with a YAML front matter block")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise ValueError(f"{name}: invalid {SKILL_MANIFEST} front matter: {e}") from e
    if not isinstance(meta, dict):
        meta = {}

    parsed: dict[str, str] = {}
    for key, limit in (
        ("name", SKILL_NAME_MAX_CHARS),
        ("description", SKILL_DESCRIPTION_MAX_CHARS),
    ):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name}: {SKILL_MANIFEST} front matter needs a non-empty {key}")
        if len(value.strip()) > limit:
            raise ValueError(f"{name}: skill {key} is longer than {limit} characters")
        parsed[key] = value.strip()
    return parsed


def _item_file_type(item: dict[str, Any], default: str | None) -> str | None:
    """A file's own ``type`` (``document`` / ``skill``) wins over the request-level one."""
    declared = item.get("type")
    if declared is None or declared == "":
        return default
    kind = str(declared).strip().lower()
    if kind not in FILE_TYPES:
        raise ValueError(f"unsupported file type {declared!r}; allowed: document, skill")
    return kind


_DATA_URL = re.compile(r"^data:[^,;]*(?:;[^,;]*)*;base64,(.*)$", re.IGNORECASE | re.DOTALL)


def _decode_base64(text: str, name: Any) -> bytes:
    try:
        return base64.b64decode(re.sub(r"\s+", "", text), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"invalid base64 content for {name}: {e}") from e


def _file_bytes(
    item: dict[str, Any], *, max_size: int | None = None, magic: bytes | None = None
) -> bytes:
    if isinstance(item.get("bytes"), bytes | bytearray):
        return bytes(item["bytes"])
    if isinstance(item.get("content_bytes"), bytes | bytearray):
        return bytes(item["content_bytes"])

    encoded = item.get("base64") or item.get("content_base64")
    if encoded:
        encoded_text = str(encoded)
        if max_size is not None and len(encoded_text) > (max_size * 4 // 3) + 16:
            raise ValueError(f"{item.get('name')} exceeds the per-file size limit")
        try:
            content = base64.b64decode(encoded_text, validate=False)
        except (binascii.Error, ValueError) as e:
            raise ValueError(f"invalid base64 content for {item.get('name')}: {e}") from e
        if max_size is not None and len(content) > max_size:
            raise ValueError(f"{item.get('name')} exceeds the per-file size limit")
        return content

    content = item.get("content")
    if isinstance(content, bytes | bytearray):
        return bytes(content)
    if content is None:
        return b""
    text = str(content)
    if re.match(r"^https?://", text.strip(), re.IGNORECASE):
        # Remote fetch is opt-in: the default deployment has no outbound egress.
        if os.getenv("KB_FETCH_REMOTE_FILES", "false").strip().lower() in {"1", "true", "on"}:
            return _download(text.strip(), max_size=max_size)
        logger.warning("KB remote file fetch disabled, storing metadata only: %s", text)
        item.setdefault("url", text.strip())
        return b""
    data_url = _DATA_URL.match(text.strip())
    if data_url:
        text = data_url.group(1)
    if data_url or magic:
        if max_size is not None and len(text) > (max_size * 4 // 3) + 16:
            raise ValueError(f"{item.get('name')} exceeds the per-file size limit")
        try:
            decoded = _decode_base64(text, item.get("name"))
        except ValueError:
            if data_url:
                raise
            decoded = None
        # A binary extension only means "decode" when the bytes carry the format's signature.
        if decoded is not None and (data_url or decoded.startswith(magic or b"")):
            if max_size is not None and len(decoded) > max_size:
                raise ValueError(f"{item.get('name')} exceeds the per-file size limit")
            return decoded
    data = text.encode("utf-8")
    if max_size is not None and len(data) > max_size:
        raise ValueError(f"{item.get('name')} exceeds the per-file size limit")
    return data


def _is_public_url(url: str) -> bool:
    """Reject loopback / link-local / private targets (basic SSRF guard)."""
    import ipaddress
    import socket

    from urllib.parse import urlparse

    if os.getenv("KB_ALLOW_PRIVATE_URLS", "false").strip().lower() in {"1", "true", "on"}:
        return True
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 80)
    except OSError:
        return False
    for info in addresses:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _remote_host_allowed(url: str) -> bool:
    """Require an explicit host allowlist for outbound KB fetches.

    DNS checks alone are vulnerable to rebinding: ``requests`` resolves the
    hostname again after ``_is_public_url``. An allowlist does not make that
    impossible, but it stops an arbitrary attacker-supplied URL from reaching
    internal services unless the operator opted that host in.
    """
    from urllib.parse import urlparse

    configured = {
        host.strip().lower()
        for host in os.getenv("KB_REMOTE_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    hostname = (urlparse(url).hostname or "").lower()
    return bool(hostname and hostname in configured)


def _download(url: str, *, max_size: int | None = None) -> bytes:
    import requests

    if not _remote_host_allowed(url):
        raise ValueError(f"remote host is not in KB_REMOTE_ALLOWED_HOSTS: {url}")
    if not _is_public_url(url):
        raise ValueError(f"refusing to fetch non-public URL: {url}")
    response = requests.get(url, timeout=30, stream=True, allow_redirects=False)
    if response.status_code != 200:
        response.close()
        raise ValueError(f"remote file returned HTTP {response.status_code}: {url}")
    response.raise_for_status()
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if max_size is not None and total > max_size:
            response.close()
            raise ValueError(f"remote file exceeds the per-file size limit: {url}")
        chunks.append(chunk)
    return b"".join(chunks)


def _paginate(
    documents: list[dict[str, Any]], page: int | None, page_size: int | None
) -> tuple[list[dict[str, Any]], int]:
    total = len(documents)
    if page and page_size:
        start = (max(page, 1) - 1) * page_size
        return documents[start : start + page_size], total
    return documents, total


def public_file_view(document: dict[str, Any]) -> dict[str, Any]:
    """Shape a file document like cloud's file detail list."""
    return {
        "id": document.get("entity_id"),
        "name": document.get("name"),
        "size": document.get("size", 0),
        "sizeMB": round(int(document.get("size") or 0) / (1024 * 1024), 6),
        "status": document.get("status"),
        "knowledgebase_id": document.get("knowledgebase_id"),
        "type": document.get("file_type"),
        "created_at": document.get("created_at"),
        **(
            {
                "skill_name": document.get("skill_name"),
                "skill_description": document.get("skill_description"),
                **(
                    {"skill_memory_id": document["skill_memory_id"]}
                    if document.get("skill_memory_id")
                    else {}
                ),
            }
            if document.get("skill_name")
            else {}
        ),
    }

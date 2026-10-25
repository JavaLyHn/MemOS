"""Deterministic parsing of user-supplied skill packages (a bare ``SKILL.md`` or a zip).

This module is deliberately dependency-light so the knowledge-base shell can use it
without importing the skill-extraction pipeline. No LLM is involved: the author's text
is stored as written.
"""

import io
import re
import stat
import zipfile

from pathlib import PurePosixPath
from typing import Any

import yaml

from memos.log import get_logger


logger = get_logger(__name__)

SKILL_MANIFEST = "SKILL.md"
SKILL_ZIP_MAX_ENTRIES = 200
SKILL_ZIP_MAX_FILE_BYTES = 10 * 1024 * 1024
SKILL_ZIP_MAX_UNPACKED_BYTES = 100 * 1024 * 1024
SKILL_MANIFEST_MAX_BYTES = 100 * 1024
SKILL_PROCEDURE_MAX_CHARS = 100 * 1024
SKILL_FILE_TEXT_MAX_CHARS = 64 * 1024
SKILL_AUX_MAX_FILES = 20

_IGNORED_ROOT = "__MACOSX"
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def parse_skill_package(content: bytes, filename: str = "") -> dict[str, Any]:
    """Parse a skill ``.md`` or ``.zip`` into the dict ``create_skill_memory_item`` expects.

    ``filename`` supplies the fallback skill name when the front matter has none.
    Raises ``ValueError`` for anything that cannot be a valid skill package.
    """
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0] if filename else ""
    if zipfile.is_zipfile(io.BytesIO(content)):
        return _parse_zip(content, stem)
    return _build_skill(_decode_manifest(content), stem, None, None)


def _decode_manifest(raw: bytes) -> str:
    if len(raw) > SKILL_MANIFEST_MAX_BYTES:
        raise ValueError(f"{SKILL_MANIFEST} is too large (limit {SKILL_MANIFEST_MAX_BYTES} bytes)")
    try:
        return raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as e:
        raise ValueError(f"{SKILL_MANIFEST} must be UTF-8 text") from e


def _scalar(value: Any) -> str:
    return str(value).strip() if isinstance(value, str | int | float) else ""


def _front_matter_fields(block: str) -> tuple[str, str]:
    name = description = ""
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        loaded = None
    if isinstance(loaded, dict):
        name = _scalar(loaded.get("name"))
        description = _scalar(loaded.get("description"))
    if name and description:
        return name, description
    # Unquoted values such as "description: Use when: x" are invalid YAML but common.
    for line in block.splitlines():
        if not name and line.startswith("name:"):
            name = line[len("name:") :].strip()
        elif not description and line.startswith("description:"):
            description = line[len("description:") :].strip()
    return name, description


def _build_skill(
    text: str,
    fallback_name: str,
    scripts: dict[str, str] | None,
    others: dict[str, str] | None,
) -> dict[str, Any]:
    name = description = ""
    body = text
    match = _FRONT_MATTER.match(text)
    if match:
        name, description = _front_matter_fields(match.group(1))
        body = text[match.end() :]
    procedure = body.strip()
    if len(procedure) > SKILL_PROCEDURE_MAX_CHARS:
        logger.warning(
            "[SKILL_PACKAGE] procedure truncated from %d to %d chars",
            len(procedure),
            SKILL_PROCEDURE_MAX_CHARS,
        )
        procedure = procedure[:SKILL_PROCEDURE_MAX_CHARS]
    return {
        "name": name or fallback_name,
        "description": description,
        "tags": [],
        "procedure": procedure,
        "experience": [],
        "preference": [],
        "examples": [],
        "tool": None,
        "scripts": scripts or None,
        "others": others or None,
    }


def _entry_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    parts = path.parts
    if path.is_absolute() or ".." in parts or (parts and re.match(r"^[A-Za-z]:", parts[0])):
        raise ValueError(f"zip entry has an unsafe path: {info.filename}")
    return tuple(p for p in parts if p != ".")


def _read_limited(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    with archive.open(info) as handle:
        return handle.read(limit + 1)


def _aux_texts(
    archive: zipfile.ZipFile,
    files: dict[tuple[str, ...], zipfile.ZipInfo],
    folder: tuple[str, ...],
    suffix: str,
) -> dict[str, str]:
    selected = sorted(
        (parts for parts in files if len(parts) == len(folder) + 1 and parts[:-1] == folder),
        key=lambda parts: parts[-1],
    )
    result: dict[str, str] = {}
    for parts in selected:
        if not parts[-1].lower().endswith(suffix):
            continue
        if len(result) >= SKILL_AUX_MAX_FILES:
            logger.warning(
                "[SKILL_PACKAGE] more than %d files in %s, rest ignored", len(result), folder
            )
            break
        raw = _read_limited(archive, files[parts], SKILL_ZIP_MAX_FILE_BYTES)
        if len(raw) > SKILL_ZIP_MAX_FILE_BYTES:
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            logger.debug("[SKILL_PACKAGE] skipped non-UTF-8 file %s", "/".join(parts))
            continue
        result[parts[-1]] = text[:SKILL_FILE_TEXT_MAX_CHARS]
    return result


def _parse_zip(content: bytes, fallback_name: str) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files: dict[tuple[str, ...], zipfile.ZipInfo] = {}
        unpacked = 0
        for info in archive.infolist():
            parts = _entry_parts(info)
            if not parts or parts[0] == _IGNORED_ROOT or info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise ValueError("zip contains encrypted entries")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"zip entry has an unsafe path: {info.filename} is a symlink")
            files[parts] = info
            unpacked += info.file_size
        if len(files) > SKILL_ZIP_MAX_ENTRIES:
            raise ValueError(f"zip has more than {SKILL_ZIP_MAX_ENTRIES} files")
        if unpacked > SKILL_ZIP_MAX_UNPACKED_BYTES:
            raise ValueError(f"zip unpacked size exceeds {SKILL_ZIP_MAX_UNPACKED_BYTES} bytes")

        manifests = sorted((p for p in files if p[-1] == SKILL_MANIFEST), key=lambda p: (len(p), p))
        if not manifests:
            raise ValueError(f"{SKILL_MANIFEST} not found in zip")
        manifest = manifests[0]
        root = manifest[:-1]
        text = _decode_manifest(_read_limited(archive, files[manifest], SKILL_MANIFEST_MAX_BYTES))
        scripts = _aux_texts(archive, files, (*root, "scripts"), ".py")
        others = _aux_texts(archive, files, (*root, "reference"), ".md")
    return _build_skill(text, fallback_name, scripts, others)

"""Project-scoped extract prompt configuration.

The console edits one complete extraction prompt per memory cube (project).
Before this module the only way to customise extraction was the request-scoped
``custom_extract_prompt`` appendix: callers could say *what* to extract for one
request, but there was nowhere to keep a full prompt.

The saved prompt replaces the built-in chat reader prompt for the duration of
one add / extract request (a ``ContextVar``, same mechanism as
``custom_extract_prompt``). It must keep the ``${conversation}`` placeholder —
the reader substitutes the actual conversation there.

Storage is a small SQLite database. It defaults to ``MOS_CUBE_PATH`` so it
lands on the PVC (``/data/memos`` in the SOC deployment); override with
``MEMOS_PROMPT_CONFIG_DB``. A single-replica deployment is assumed, the same
limitation as the rest of the SQLite state in this service.
"""

from __future__ import annotations

import os
import sqlite3
import threading

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from memos import settings
from memos.log import get_logger
from memos.templates.mem_reader_prompts import SIMPLE_STRUCT_MEM_READER_PROMPT_ZH


if TYPE_CHECKING:
    from collections.abc import Iterator


logger = get_logger(__name__)

PROMPT_PLACEHOLDER = "${conversation}"
MAX_EXTRACT_PROMPT_CHARS = 20000
EXTRACTION_TYPES: tuple[str, ...] = ("text_mem", "pref_mem", "event_mem")

_DB_LOCK = threading.Lock()
_base_prompt: ContextVar[str | None] = ContextVar("base_extract_prompt", default=None)


def default_extract_prompt() -> str:
    """The prompt used when a project has never saved one."""
    return SIMPLE_STRUCT_MEM_READER_PROMPT_ZH


def normalize_extract_prompt(value: str) -> str:
    """Validate a prompt before it is saved.

    ``${conversation}`` is mandatory: without it the reader would call the model
    with a prompt that contains no conversation, and extraction would silently
    return nothing.
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("prompt must not be empty")
    if len(text) > MAX_EXTRACT_PROMPT_CHARS:
        raise ValueError(f"prompt exceeds {MAX_EXTRACT_PROMPT_CHARS} characters")
    if PROMPT_PLACEHOLDER not in text:
        raise ValueError(f"prompt must contain {PROMPT_PLACEHOLDER}")
    return text


def _db_path() -> Path:
    configured = os.getenv("MEMOS_PROMPT_CONFIG_DB", "").strip()
    if configured:
        return Path(configured)
    base = os.getenv("MOS_CUBE_PATH", "").strip() or str(settings.MEMOS_DIR)
    return Path(base) / "extract_prompts.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS extract_prompt_configs ("
        "mem_cube_id TEXT PRIMARY KEY, prompt TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    return conn


def get_saved_prompt(mem_cube_id: str) -> tuple[str, str] | None:
    """Return ``(prompt, updated_at)`` for a project, or ``None`` when unset."""
    if not mem_cube_id:
        return None
    conn = _connect()
    try:
        with _DB_LOCK:
            row = conn.execute(
                "SELECT prompt, updated_at FROM extract_prompt_configs WHERE mem_cube_id = ?",
                (mem_cube_id,),
            ).fetchone()
    finally:
        conn.close()
    return (row[0], row[1]) if row else None


def save_prompt(mem_cube_id: str, prompt: str) -> str:
    """Validate and persist a project prompt; returns the stored ``updated_at``."""
    if not mem_cube_id:
        raise ValueError("mem_cube_id must not be empty")
    text = normalize_extract_prompt(prompt)
    updated_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        with _DB_LOCK, conn:
            conn.execute(
                "INSERT INTO extract_prompt_configs (mem_cube_id, prompt, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(mem_cube_id) DO UPDATE SET "
                "prompt = excluded.prompt, updated_at = excluded.updated_at",
                (mem_cube_id, text, updated_at),
            )
    finally:
        conn.close()
    return updated_at


def delete_prompt(mem_cube_id: str) -> bool:
    """Drop a saved prompt (reset to default); reports whether a row existed."""
    if not mem_cube_id:
        return False
    conn = _connect()
    try:
        with _DB_LOCK, conn:
            cursor = conn.execute(
                "DELETE FROM extract_prompt_configs WHERE mem_cube_id = ?", (mem_cube_id,)
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


@contextmanager
def use_base_extract_prompt(prompt: str | None) -> Iterator[None]:
    """Make ``prompt`` the chat reader template for the current context."""
    token = _base_prompt.set(prompt)
    try:
        yield
    finally:
        _base_prompt.reset(token)


def current_base_extract_prompt() -> str | None:
    return _base_prompt.get()


@contextmanager
def use_project_extract_prompt(mem_cube_id: str | None) -> Iterator[None]:
    """Load and apply a project's saved prompt.

    A missing row means "use the built-in prompt". Storage errors are logged and
    ignored: a broken config database must not block memory writes.
    """
    prompt: str | None = None
    try:
        saved = get_saved_prompt(mem_cube_id or "")
        if saved:
            prompt = saved[0]
    except Exception:
        logger.warning(
            "[PromptConfig] failed to load prompt for %r; using default", mem_cube_id, exc_info=True
        )
    with use_base_extract_prompt(prompt):
        yield

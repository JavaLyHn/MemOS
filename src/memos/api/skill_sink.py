"""Knowledge-base shell hook that turns an uploaded skill file into a recallable SkillMemory."""

import io
import tempfile
import zipfile

from pathlib import Path
from typing import Any

from memos.api.handlers.skill_cleanup import (
    delete_skill_files,
    skill_refs_for_file_ids,
    skill_refs_from_nodes,
)
from memos.log import get_logger
from memos.mem_reader.read_skill_memory import skill_store
from memos.mem_reader.read_skill_memory.skill_package import SKILL_MANIFEST, parse_skill_package


logger = get_logger(__name__)


class SkillMemorySink:
    """Creates and removes the SkillMemory (and its downloadable zip) behind a KB skill file."""

    def __init__(
        self,
        text_mem: Any,
        embedder: Any,
        skills_dir_config: dict[str, Any] | None = None,
        oss_config: dict[str, Any] | None = None,
    ):
        self.text_mem = text_mem
        self.embedder = embedder
        self.skills_dir_config = skills_dir_config or skill_store.skills_dir_config_from_env()
        self.oss_config = oss_config

    def add_skill(
        self,
        *,
        user_name: str,
        owner_user_id: str | None,
        file_id: str,
        name: str,
        content: bytes,
    ) -> dict[str, Any]:
        from memos.mem_reader.read_skill_memory.process_skill_memory import (
            create_oss_client,
            create_skill_memory_item,
        )

        skill = parse_skill_package(content, name)
        user_id = owner_user_id or user_name
        backend = skill_store.storage_backend()
        client = create_oss_client(self.oss_config or {}) if backend == "OSS" else None

        with tempfile.TemporaryDirectory(prefix="kb_skill_") as tmp:
            zip_path = Path(tmp) / skill_store.unique_zip_name(skill["name"])
            zip_path.write_bytes(
                content if zipfile.is_zipfile(io.BytesIO(content)) else _wrap(content)
            )
            url = skill_store.publish_skill(
                zip_path,
                user_id,
                backend=backend,
                skills_dir_config=self.skills_dir_config,
                oss_client=client,
            )
        if not url:
            raise RuntimeError("skill file could not be published")

        skill.update({"url": url, "skill_source": "user_upload"})
        try:
            item = create_skill_memory_item(
                skill, {"user_id": user_id, "session_id": "knowledgebase"}, self.embedder
            )
            item.metadata.file_ids = [file_id]
            item.metadata.info = {**(item.metadata.info or {}), "file_id": file_id}
            self.text_mem.add([item], user_name=user_name)
        except Exception:
            self._delete_file(url, user_id, backend, client)
            raise
        # The graph writers swallow their own errors, so read the node back. A failed read says
        # nothing about the write, so it leaves the zip alone.
        if not self.text_mem.get_by_ids([item.id], user_name=user_name):
            self._delete_file(url, user_id, backend, client)
            raise RuntimeError("skill memory was not stored")
        return {"skill_memory_id": item.id, "skill_url": url}

    def remove_skill(
        self, *, user_name: str, owner_user_id: str | None, file: dict[str, Any]
    ) -> None:
        file_id = file["entity_id"]
        refs = skill_refs_for_file_ids(self.text_mem, [file_id], [user_name])
        recorded_id = file.get("skill_memory_id")
        if recorded_id and recorded_id not in {r.node_id for r in refs}:
            refs += skill_refs_from_nodes(self.text_mem.get_by_ids([recorded_id]))

        self.text_mem.delete_by_filter(writable_cube_ids=[user_name], file_ids=[file_id])
        if recorded_id:
            self.text_mem.delete_by_memory_ids([recorded_id])
        delete_skill_files(self.text_mem, refs)

    def _delete_file(self, url: str, user_id: str, backend: str, client: Any) -> None:
        try:
            skill_store.delete_skill_by_url(
                url,
                user_id,
                backend=backend,
                skills_dir_config=self.skills_dir_config,
                oss_client=client,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[KB_SKILL] could not clean up %s: %s", url, e)


def _wrap(markdown: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(SKILL_MANIFEST, markdown)
    return buffer.getvalue()

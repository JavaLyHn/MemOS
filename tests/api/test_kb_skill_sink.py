"""Knowledge-base skill uploads become recallable SkillMemory nodes, and go away with the file."""

import io
import zipfile

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from memos.api.cloud_store import JsonMetadataStore
from memos.api.handlers.formatters_handler import format_memory_item, post_process_textual_mem
from memos.api.knowledge_base import KnowledgeBaseService, NoopIngestor, public_file_view
from memos.api.skill_sink import SkillMemorySink
from memos.mem_reader.read_skill_memory import skill_store
from memos.mem_reader.read_skill_memory.skill_package import parse_skill_package


BODY = "# PDF toolkit\n\nUse this whenever a PDF must be read.\n\n## Steps\n\n1. Extract the text.\n2. Summarise."
SKILL_MD = f"---\nname: pdf-toolkit\ndescription: Extract text from PDFs\n---\n\n{BODY}\n"


class FakeGraph:
    def __init__(self):
        self.nodes: dict[str, dict[str, Any]] = {}

    def get_by_metadata(self, filters, user_name=None, filter=None, knowledgebase_ids=None, **_):
        found = []
        for node in self.nodes.values():
            if knowledgebase_ids and node["user_name"] not in knowledgebase_ids:
                continue
            meta = node["metadata"]
            if all(
                meta.get(f["field"]) == f["value"]
                if f["op"] == "="
                else any(x in (meta.get(f["field"]) or []) for x in f["value"])
                for f in filters
            ):
                found.append(node["id"])
        return found


class FakeTextMem:
    def __init__(self):
        self.graph_store = FakeGraph()
        self.items: dict[str, Any] = {}
        self.fail_add = False
        self.fail_read = False

    def add(self, memories, user_name=None, **_):
        if self.fail_add == "silent":
            return []
        if self.fail_add:
            raise RuntimeError("graph down")
        for item in memories:
            self.items[item.id] = item
            self.graph_store.nodes[item.id] = {
                "id": item.id,
                "memory": item.memory,
                "user_name": user_name,
                "metadata": item.metadata.model_dump(),
            }
        return [m.id for m in memories]

    def get_by_ids(self, memory_ids, user_name=None):
        if self.fail_read:
            raise RuntimeError("graph read timed out")
        return [self.graph_store.nodes[i] for i in memory_ids if i in self.graph_store.nodes]

    def delete_by_filter(self, writable_cube_ids=None, file_ids=None, filter=None):
        for node in list(self.graph_store.nodes.values()):
            if writable_cube_ids and node["user_name"] not in writable_cube_ids:
                continue
            if file_ids and not all(
                f in (node["metadata"].get("file_ids") or []) for f in file_ids
            ):
                continue
            self.graph_store.nodes.pop(node["id"])

    def delete_by_memory_ids(self, memory_ids):
        for mid in memory_ids:
            self.graph_store.nodes.pop(mid, None)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    monkeypatch.setenv("SKILLS_REPO_BACKEND", "LOCAL")
    monkeypatch.setenv("SKILLS_LOCAL_DIR", str(tmp_path / "local"))
    monkeypatch.delenv("SKILLS_DOWNLOAD_BASE_URL", raising=False)
    config = skill_store.skills_dir_config_from_env()
    embedder = MagicMock()
    embedder.embed.side_effect = lambda texts: [[float(len(t))] for t in texts]
    text_mem = FakeTextMem()
    service = KnowledgeBaseService(
        store=JsonMetadataStore(tmp_path / "store"),
        storage_dir=tmp_path / "kb",
        ingestor=NoopIngestor(),
        skill_sink=SkillMemorySink(text_mem, embedder, config),
    )
    return service, text_mem, embedder, config


def _kb(service, tenant="tenant-1"):
    return service.create(user_name=tenant, name="skills", owner_user_id=tenant)


def _zip(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path, data in entries.items():
            archive.writestr(path, data)
    return buf.getvalue()


def _upload(service, name, content, tenant="tenant-1", user_id="user-a", kb=None):
    kb = kb or _kb(service, tenant)
    return service.add_files(
        user_name=tenant,
        knowledgebase_id=kb["entity_id"],
        files=[{"name": name, "bytes": content}],
        file_type="skill",
        owner_user_id=user_id,
    )[0]


def test_markdown_upload_creates_a_whole_skill_node(world):
    service, text_mem, embedder, _ = world

    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())

    assert doc["status"] == "stored"
    node = text_mem.graph_store.nodes[doc["skill_memory_id"]]
    meta = node["metadata"]
    assert node["user_name"] == "tenant-1"
    assert (meta["memory_type"], meta["status"]) == ("SkillMemory", "activated")
    assert (meta["name"], meta["description"]) == ("pdf-toolkit", "Extract text from PDFs")
    assert meta["procedure"] == BODY
    assert meta["skill_source"] == "user_upload"
    assert meta["file_ids"] == [doc["entity_id"]]
    assert meta["user_id"] == "user-a"
    assert meta["url"] == doc["skill_url"]
    embedder.embed.assert_called_once_with(["pdf-toolkit\nExtract text from PDFs"])
    assert public_file_view(doc)["skill_memory_id"] == doc["skill_memory_id"]


def test_published_file_is_a_zip_the_parser_reads_back(world):
    service, _, _, config = world

    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())

    path = skill_store.local_path_for_url(doc["skill_url"], "user-a", config)
    assert path.is_file()
    assert path.parent.parent.name == "skills"
    assert parse_skill_package(path.read_bytes(), path.name)["procedure"] == BODY


def test_zip_upload_publishes_the_original_bytes_and_keeps_scripts(world):
    service, text_mem, _, config = world
    package = _zip(
        {"SKILL.md": SKILL_MD, "scripts/run.py": "print('x')\n", "reference/api.md": "# API\n"}
    )

    doc = _upload(service, "pdf-toolkit.zip", package)

    meta = text_mem.graph_store.nodes[doc["skill_memory_id"]]["metadata"]
    assert meta["scripts"] == {"run.py": "print('x')\n"}
    assert meta["others"] == {"api.md": "# API\n"}
    path = skill_store.local_path_for_url(doc["skill_url"], "user-a", config)
    assert path.read_bytes() == package


def test_uploaded_skill_is_routed_to_the_skill_bucket_with_its_url(world):
    service, text_mem, _, _ = world
    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())
    formatted = format_memory_item(text_mem.items[doc["skill_memory_id"]])

    result = post_process_textual_mem(
        {"text_mem": [], "tool_mem": [], "skill_mem": [], "pref_mem": [], "dream_mem": []},
        [formatted],
        "tenant-1",
    )

    [bucket] = result["skill_mem"]
    [memory] = bucket["memories"]
    assert memory["metadata"]["url"] == doc["skill_url"]
    assert memory["metadata"]["procedure"] == BODY


def test_same_named_skills_of_two_users_do_not_overwrite_each_other(world):
    service, _, _, config = world
    kb = _kb(service)
    first = _upload(service, "pdf-toolkit.md", SKILL_MD.encode(), user_id="user-a", kb=kb)
    second = _upload(
        service,
        "pdf-toolkit.md",
        SKILL_MD.replace("Summarise", "Report").encode(),
        user_id="user-b",
        kb=kb,
    )

    assert first["skill_memory_id"] != second["skill_memory_id"]
    path_a = skill_store.local_path_for_url(first["skill_url"], "user-a", config)
    path_b = skill_store.local_path_for_url(second["skill_url"], "user-b", config)
    assert path_a != path_b
    assert path_a.is_file()
    assert path_b.is_file()
    assert "Report" in parse_skill_package(path_b.read_bytes(), "x.zip")["procedure"]
    assert "Report" not in parse_skill_package(path_a.read_bytes(), "x.zip")["procedure"]


def test_deleting_the_file_removes_node_and_skill_file(world):
    service, text_mem, _, config = world
    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())
    path = skill_store.local_path_for_url(doc["skill_url"], "user-a", config)
    other = _upload(service, "other.md", SKILL_MD.replace("pdf-toolkit", "other").encode())

    deleted = service.delete_files(user_name="tenant-1", file_ids=[doc["entity_id"]])

    assert deleted == 1
    assert doc["skill_memory_id"] not in text_mem.graph_store.nodes
    assert not path.exists()
    assert other["skill_memory_id"] in text_mem.graph_store.nodes
    assert skill_store.local_path_for_url(other["skill_url"], "user-a", config).is_file()
    assert service.get_file(user_name="tenant-1", file_id=doc["entity_id"]) is None


def test_deleting_the_knowledge_base_removes_its_skills(world):
    service, text_mem, _, config = world
    kb = _kb(service)
    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode(), kb=kb)
    path = skill_store.local_path_for_url(doc["skill_url"], "user-a", config)

    assert service.delete(user_name="tenant-1", knowledgebase_id=kb["entity_id"]) is True

    assert text_mem.graph_store.nodes == {}
    assert not path.exists()


def test_a_failed_node_delete_keeps_the_file_record_so_it_can_be_retried(world):
    service, text_mem, _, config = world
    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())

    def boom(**_kwargs):
        raise RuntimeError("graph down")

    text_mem.delete_by_filter = boom

    assert service.delete_files(user_name="tenant-1", file_ids=[doc["entity_id"]]) == 0
    assert service.get_file(user_name="tenant-1", file_id=doc["entity_id"]) is not None
    assert skill_store.local_path_for_url(doc["skill_url"], "user-a", config).is_file()


@pytest.mark.parametrize(
    ("failure", "reason"), [(True, "graph down"), ("silent", "was not stored")]
)
def test_sink_failure_keeps_the_file_but_marks_it_failed_and_leaves_no_zip(world, failure, reason):
    service, text_mem, _, config = world
    text_mem.fail_add = failure

    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())

    assert doc["status"] == "failed"
    assert reason in doc["error"]
    assert Path(doc["storage_path"]).read_bytes() == SKILL_MD.encode()
    assert text_mem.graph_store.nodes == {}
    assert not list(skill_store.local_skill_layout(config)[0].rglob("*.zip"))


def test_a_failed_read_back_keeps_the_zip_of_a_node_that_may_exist(world):
    service, text_mem, _, config = world
    text_mem.fail_read = True

    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())

    assert doc["status"] == "failed"
    assert text_mem.graph_store.nodes
    assert len(list(skill_store.local_skill_layout(config)[0].rglob("*.zip"))) == 1


def test_non_skill_uploads_never_touch_the_sink(world):
    service, text_mem, embedder, _ = world
    kb = _kb(service)

    service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "notes.md", "content": "hello"}],
    )

    assert text_mem.graph_store.nodes == {}
    embedder.embed.assert_not_called()


def test_without_a_sink_skill_uploads_only_store_bytes(tmp_path):
    service = KnowledgeBaseService(
        store=JsonMetadataStore(tmp_path / "store"),
        storage_dir=tmp_path / "kb",
        ingestor=NoopIngestor(),
    )

    doc = _upload(service, "pdf-toolkit.md", SKILL_MD.encode())

    assert doc["status"] == "stored"
    assert "skill_memory_id" not in doc

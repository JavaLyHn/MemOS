from types import SimpleNamespace

from memos.api.handlers import memory_handler
from memos.api.product_models import GetMemoryRequest
from memos.graph_dbs.neo4j import Neo4jGraphDB
from memos.memories.textual.item import TextualMemoryItem, TreeNodeTextualMemoryMetadata


def _stored_node(node_id, **props):
    """A node the way the Neo4j driver hands it back, after the store's own parsing."""
    raw = {
        "id": node_id,
        "memory": f"skill {node_id}",
        "memory_type": "SkillMemory",
        "status": "activated",
        "user_name": "cube-1",
        "created_at": "2026-10-21T00:00:00+00:00",
        "updated_at": "2026-10-21T00:00:00+00:00",
        "sources": [],
        **props,
    }
    return Neo4jGraphDB._parse_node(object(), raw)


class FakeTextMem:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_all(self, *, memory_type=None, **_):
        picked = [n for n in self.nodes if n["metadata"]["memory_type"] in (memory_type or [])]
        return {"nodes": picked, "total_nodes": len(picked)}

    def get(self, memory_id, user_name=None):
        node = next(n for n in self.nodes if n["id"] == memory_id)
        return TextualMemoryItem(
            id=node["id"],
            memory=node["memory"],
            metadata=TreeNodeTextualMemoryMetadata(**node["metadata"]),
        )

    def get_by_ids(self, memory_ids, user_name=None):
        return [n for n in self.nodes if n["id"] in memory_ids]


NEW_ID = "7d2b0f5e-1c3a-4f6b-9a1e-2b6d8c4e9a01"
OLD_ID = "0b9c4a7e-5d1f-4e2a-8c3b-6a7f1d2e3b04"
STORED = _stored_node(NEW_ID, url="https://files.example/skills/new.zip")
LEGACY = _stored_node(OLD_ID)
CUBE = SimpleNamespace(text_mem=FakeTextMem([STORED, LEGACY]))


def test_the_memory_list_returns_each_skills_url_and_an_empty_one_for_a_legacy_node():
    request = GetMemoryRequest(mem_cube_id="cube-1", user_id="u1")

    skills = memory_handler.handle_get_memories(request, CUBE).data["skill_mem"][0]["memories"]

    assert {n["id"]: n["metadata"]["url"] for n in skills} == {
        NEW_ID: "https://files.example/skills/new.zip",
        OLD_ID: "",
    }


def test_the_single_and_by_ids_reads_return_the_skill_url_too():
    one = memory_handler.handle_get_memory(NEW_ID, CUBE).data
    many = memory_handler.handle_get_memory_by_ids([NEW_ID, OLD_ID], CUBE).data["memories"]

    assert one["metadata"]["url"] == "https://files.example/skills/new.zip"
    assert [n["metadata"]["url"] for n in many] == ["https://files.example/skills/new.zip", ""]
    assert LEGACY["metadata"].get("url") is None

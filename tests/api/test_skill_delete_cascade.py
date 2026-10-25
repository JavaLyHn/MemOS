"""Deleting memories also deletes the skill zips their SkillMemory nodes point to."""

from typing import Any
from unittest.mock import Mock

import pytest

from memos.api.handlers.memory_handler import handle_delete_memories
from memos.api.product_models import DeleteMemoryRequest
from memos.mem_reader.read_skill_memory import skill_store


class FakeGraph:
    def __init__(self, nodes: list[dict[str, Any]]):
        self.nodes = {n["id"]: n for n in nodes}
        self.delete_is_silent_noop = False

    def get_by_metadata(self, filters, user_name=None, filter=None, knowledgebase_ids=None, **_):
        tenants = set(knowledgebase_ids or [])
        found = []
        for node in self.nodes.values():
            meta = node["metadata"]
            if tenants and node["user_name"] not in tenants:
                continue
            ok = True
            for f in filters:
                value = meta.get(f["field"])
                if f["op"] == "=":
                    ok &= value == f["value"]
                elif f["op"] == "contains":
                    ok &= any(x in (value or []) for x in f["value"])
            if ok:
                found.append(node["id"])
        return found

    def export_graph(self, user_name=None, filter=None, page_size=None, status=None, **_):
        return {"nodes": [n for n in self.nodes.values() if n["user_name"] == user_name]}


class FakeTextMem:
    def __init__(self, nodes):
        self.graph_store = FakeGraph(nodes)

    def get_by_ids(self, memory_ids, user_name=None):
        return [self.graph_store.nodes[i] for i in memory_ids if i in self.graph_store.nodes]

    def delete_by_memory_ids(self, memory_ids):
        if self.graph_store.delete_is_silent_noop:
            return
        for mid in memory_ids:
            self.graph_store.nodes.pop(mid, None)

    def delete_by_filter(self, writable_cube_ids=None, file_ids=None, filter=None):
        if self.graph_store.delete_is_silent_noop:
            return
        for node in list(self.graph_store.nodes.values()):
            if writable_cube_ids and node["user_name"] not in writable_cube_ids:
                continue
            if file_ids and not all(
                f in (node["metadata"].get("file_ids") or []) for f in file_ids
            ):
                continue
            self.graph_store.nodes.pop(node["id"])


class FakeCube:
    def __init__(self, nodes):
        self.text_mem = FakeTextMem(nodes)
        self.pref_mem = None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    monkeypatch.setenv("SKILLS_REPO_BACKEND", "LOCAL")
    monkeypatch.setenv("SKILLS_LOCAL_DIR", str(tmp_path / "local"))
    monkeypatch.delenv("SKILLS_DOWNLOAD_BASE_URL", raising=False)
    return tmp_path, skill_store.skills_dir_config_from_env()


def _zip_file(tmp_path, name, content=b"PK"):
    path = tmp_path / "work" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _skill_node(tmp_path, config, node_id, user_id="u1", file_ids=None, tenant="cube-1", url=None):
    if url is None:
        url = skill_store.publish_local_skill(
            _zip_file(tmp_path, f"{node_id}.zip"), user_id, config
        )
    return {
        "id": node_id,
        "memory": "desc",
        "user_name": tenant,
        "metadata": {
            "memory_type": "SkillMemory",
            "user_id": user_id,
            "url": url,
            "file_ids": file_ids or [],
            "status": "activated",
        },
    }


def _plain_node(node_id, tenant="cube-1"):
    return {
        "id": node_id,
        "memory": "fact",
        "user_name": tenant,
        "metadata": {"memory_type": "LongTermMemory", "user_id": "u1", "status": "activated"},
    }


def _file_of(node, config, user_id="u1"):
    return skill_store.local_path_for_url(node["metadata"]["url"], user_id, config)


def test_delete_by_memory_ids_removes_the_skill_file(env):
    tmp_path, config = env
    skill = _skill_node(tmp_path, config, "s1")
    cube = FakeCube([skill, _plain_node("m1")])
    path = _file_of(skill, config)
    assert path.is_file()

    resp = handle_delete_memories(DeleteMemoryRequest(memory_ids=["s1", "m1"]), cube)

    assert resp.data["status"] == "success"
    assert not path.exists()
    assert cube.text_mem.graph_store.nodes == {}


def test_delete_by_memory_ids_leaves_files_of_other_skills(env):
    tmp_path, config = env
    gone = _skill_node(tmp_path, config, "s1")
    kept = _skill_node(tmp_path, config, "s2")
    cube = FakeCube([gone, kept])

    handle_delete_memories(DeleteMemoryRequest(memory_ids=["s1"]), cube)

    assert not _file_of(gone, config).exists()
    assert _file_of(kept, config).is_file()


def test_a_rewritten_url_cannot_delete_another_users_file(env):
    tmp_path, config = env
    victim = _skill_node(tmp_path, config, "victim", user_id="u2", tenant="cube-2")
    attacker = _skill_node(
        tmp_path, config, "attacker", user_id="u1", url=victim["metadata"]["url"]
    )
    cube = FakeCube([victim, attacker])

    handle_delete_memories(DeleteMemoryRequest(memory_ids=["attacker"]), cube)

    assert _file_of(victim, config, "u2").is_file()


def test_delete_by_file_ids_removes_matching_skill_nodes_and_files(env):
    tmp_path, config = env
    from_file = _skill_node(tmp_path, config, "s1", file_ids=["f1"])
    other_file = _skill_node(tmp_path, config, "s2", file_ids=["f2"])
    cube = FakeCube([from_file, other_file])

    resp = handle_delete_memories(
        DeleteMemoryRequest(file_ids=["f1"], writable_cube_ids=["cube-1"]), cube
    )

    assert resp.data["status"] == "success"
    assert set(cube.text_mem.graph_store.nodes) == {"s2"}
    assert not _file_of(from_file, config).exists()
    assert _file_of(other_file, config).is_file()


def test_delete_by_filter_removes_skill_files_but_keeps_frozen_ones(env):
    tmp_path, config = env
    normal = _skill_node(tmp_path, config, "s1")
    frozen = _skill_node(tmp_path, config, "s2")
    frozen["metadata"]["status"] = "frozen"
    cube = FakeCube([normal, frozen])

    resp = handle_delete_memories(
        DeleteMemoryRequest(user_id="cube-1", writable_cube_ids=["cube-1"]), cube
    )

    assert resp.data["status"] == "success"
    assert not _file_of(normal, config).exists()
    assert _file_of(frozen, config).is_file()


def test_files_are_kept_when_the_node_delete_did_not_happen(env):
    tmp_path, config = env
    skill = _skill_node(tmp_path, config, "s1")
    cube = FakeCube([skill])
    cube.text_mem.graph_store.delete_is_silent_noop = True

    handle_delete_memories(DeleteMemoryRequest(memory_ids=["s1"]), cube)

    assert _file_of(skill, config).is_file()


def test_file_cleanup_errors_do_not_fail_the_delete(env, monkeypatch):
    tmp_path, config = env
    skill = _skill_node(tmp_path, config, "s1")
    cube = FakeCube([skill])

    def boom(*_args, **_kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(skill_store, "delete_skill_by_url", boom)

    resp = handle_delete_memories(DeleteMemoryRequest(memory_ids=["s1"]), cube)

    assert resp.data["status"] == "success"
    assert cube.text_mem.graph_store.nodes == {}


def test_mock_backed_stores_are_unaffected():
    cube = Mock()
    cube.text_mem = Mock()
    cube.pref_mem = None

    resp = handle_delete_memories(
        DeleteMemoryRequest(file_ids=["f"], writable_cube_ids=["c"]), cube
    )

    assert resp.data["status"] == "success"
    cube.text_mem.delete_by_filter.assert_called_once()

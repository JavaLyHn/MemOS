"""A tool-using conversation becomes recallable skill and tool memories, and re-sending it stays tidy.

The reader, the real ``MemoryManager`` and the real ``/product/search`` formatters run for real. Only the
LLM (scripted), the graph store (an in-memory stand-in that applies Neo4j's own value rules) and the
searcher (reads the same store) are faked. The ordinary-fact and preference extractors are switched off:
this file is about the tool and skill paths.
"""

import json

from unittest.mock import MagicMock

import pytest

from memos.api.handlers.formatters_handler import format_memory_item, post_process_textual_mem
from memos.graph_dbs.neo4j import (
    _flatten_info_fields,
    _prepare_node_metadata,
    _sanitize_neo4j_metadata,
)
from memos.mem_reader import multi_modal_struct
from memos.mem_reader.multi_modal_struct import MultiModalStructMemReader
from memos.mem_reader.read_multi_modal.multi_modal_parser import MultiModalParser
from memos.mem_reader.read_skill_memory import process_skill_memory, skill_store
from memos.mem_reader.read_skill_memory.skill_package import parse_skill_package
from memos.memories.textual.item import TextualMemoryItem
from memos.memories.textual.tree_text_memory.organize.manager import MemoryManager
from memos.types.general_types import UserContext


TENANT = "cube-1"
USER = "user-a"
SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        },
    }
]
SKILL = {
    "name": "Release Notes Lookup",
    "description": "Find and summarise the latest release notes of a library",
    "trigger": ["release notes"],
    "procedure": "1. Search the web for the release notes. 2. Summarise the changes.",
    "experience": ["Prefer the official changelog"],
    "preference": [],
    "update": False,
    "old_memory_id": "",
    "examples": ["# Summary\n- ..."],
    "scripts": None,
    "tool": None,
    "others": {"reference.md": "How to read a changelog"},
}
TRAJECTORY = [
    {
        "correctness": "success",
        "trajectory": "find release notes -> search_web -> summarised 0.11.4",
        "experience": "when asked for release notes, then search the web first",
        "tool_used_status": [
            {
                "used_tool": "search_web",
                "success_rate": 1.0,
                "error_type": "",
                "tool_experience": "query with the library name",
            }
        ],
    }
]


def conversation(with_schema=False, schema=SCHEMA):
    system = (
        [{"role": "system", "content": f"Tools.<tool_schema>{json.dumps(schema)}</tool_schema>"}]
        if with_schema
        else []
    )
    return [
        *system,
        {"role": "user", "content": "Find the latest release notes of pdfplumber and summarise."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search_web", "arguments": '{"q": "pdfplumber notes"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "pdfplumber 0.11.4 fixes tables"},
        {"role": "assistant", "content": "Release 0.11.4 fixes table extraction."},
    ]


class ScriptedLLM:
    def __init__(self):
        self.skill = dict(SKILL)
        self.prompts: list[str] = []

    def generate(self, messages, **_kwargs):
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        if "tool experience extraction expert" in prompt:
            return json.dumps(TRAJECTORY)
        if "# Context (Conversation Records)" in prompt:
            chunk = [{"task_id": 1, "task_name": "Release Notes", "message_indices": [[0, 3]]}]
            return json.dumps(chunk)
        if "skill abstraction and knowledge extraction" in prompt:
            return json.dumps(self.skill)
        return "release notes lookup"


class FakeGraph:
    """Stores nodes the way ``Neo4jCommunityGraphDB.add_nodes_batch`` does, and reads them back."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}

    def add_nodes_batch(self, nodes, user_name=None):
        for node in nodes:
            props = _sanitize_neo4j_metadata(
                _flatten_info_fields(_prepare_node_metadata(dict(node["metadata"])))
            )
            props.pop("embedding", None)
            self.nodes[node["id"]] = {"memory": node["memory"], "props": props, "tenant": user_name}

    def delete_node_by_prams(self, memory_ids=None, **_):
        for node_id in memory_ids or []:
            self.nodes.pop(node_id, None)

    def _as_node(self, node_id):
        node = self.nodes[node_id]
        props = dict(node["props"])
        props["sources"] = [json.loads(s) for s in props.get("sources", [])]
        return {"id": node_id, "memory": node["memory"], "metadata": props}

    def get_node(self, node_id, user_name=None, **_):
        node = self.nodes.get(node_id)
        return self._as_node(node_id) if node and user_name in (None, node["tenant"]) else None

    def get_nodes(self, ids, **_):
        return [self._as_node(i) for i in ids if i in self.nodes]

    def get_by_metadata(self, filters, user_name=None, status=None, **_):
        wanted = {f["field"]: f["value"] for f in filters}
        return [
            node_id
            for node_id, node in self.nodes.items()
            if node["tenant"] == user_name
            and all(node["props"].get(k) == v for k, v in wanted.items())
            and (status is None or node["props"].get("status", "activated") == status)
        ]

    def update_node(self, node_id, fields, user_name=None):
        self.nodes[node_id]["props"].update(fields)

    def add_edge(self, *_args, **_kwargs):
        pass

    def recall(self, tenant, memory_types):
        return [
            TextualMemoryItem.from_dict(self._as_node(node_id))
            for node_id, node in self.nodes.items()
            if node["tenant"] == tenant
            and node["props"]["memory_type"] in memory_types
            and node["props"].get("status", "activated") == "activated"
        ]

    def count(self, memory_type):
        return sum(1 for n in self.nodes.values() if n["props"]["memory_type"] == memory_type)


class RecallSearcher:
    def __init__(self, graph):
        self.graph = graph

    def search(self, query, top_k=5, user_name=None, **_):
        return self.graph.recall(user_name, {"SkillMemory", "ToolSchemaMemory"})


class World:
    def __init__(self, tmp_path):
        self.config = skill_store.skills_dir_config_from_env()
        self.graph = FakeGraph()
        self.llm = ScriptedLLM()
        self.manager = MemoryManager(self.graph, MagicMock(), MagicMock())
        embedder = MagicMock()
        embedder.embed.side_effect = lambda texts: [[float(len(t))] for t in texts]
        reader = object.__new__(MultiModalStructMemReader)
        reader.embedder = embedder
        reader.llm = reader.general_llm = self.llm
        reader.multi_modal_parser = MultiModalParser(embedder=embedder, llm=self.llm)
        reader.chat_window_max_tokens = 1024
        reader._count_tokens = lambda text: len(text.split())
        reader.save_rawfile = False
        reader.searcher = RecallSearcher(self.graph)
        reader.graph_db = self.graph
        reader.oss_config = None
        reader.skills_dir_config = self.config
        reader._process_string_fine = lambda *_a, **_k: []
        self.reader = reader

    def add(self, messages, tenant=TENANT, user=USER):
        context = UserContext(user_id=user, mem_cube_id=tenant, session_id="s1")
        items = self.reader._process_multi_modal_data(
            messages,
            {"user_id": user, "session_id": "s1"},
            mode="fine",
            user_context=context,
            user_name=tenant,
        )
        self.manager.add(items, user_name=tenant, mode="async")
        return items

    def search(self, tenant=TENANT):
        recalled = self.graph.recall(
            tenant, {"SkillMemory", "ToolTrajectoryMemory", "ToolSchemaMemory"}
        )
        buckets = {"text_mem": [], "tool_mem": [], "skill_mem": [], "pref_mem": [], "dream_mem": []}
        post_process_textual_mem(buckets, [format_memory_item(i) for i in recalled], tenant)
        return {
            "skills": [m for b in buckets["skill_mem"] for m in b["memories"]],
            "tools": [m for b in buckets["tool_mem"] for m in b["memories"]],
        }

    def zip_of(self, skill):
        return skill_store.local_path_for_url(skill["metadata"]["url"], USER, self.config)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    monkeypatch.setenv("SKILLS_REPO_BACKEND", "LOCAL")
    monkeypatch.setenv("SKILLS_LOCAL_DIR", str(tmp_path / "local"))
    monkeypatch.setenv("SKILLS_LOCAL_TMP_DIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", "1")
    monkeypatch.delenv("SKILLS_DOWNLOAD_BASE_URL", raising=False)
    monkeypatch.setattr(multi_modal_struct, "process_preference_fine", lambda *_a, **_k: [])
    return World(tmp_path)


def test_a_tool_conversation_is_recalled_as_a_skill_with_a_downloadable_zip(world):
    world.add(conversation())

    [skill] = world.search()["skills"]

    meta = skill["metadata"]
    assert (meta["name"], meta["skill_source"]) == (SKILL["name"], "auto_create")
    assert meta["procedure"] == SKILL["procedure"]
    assert skill["memory"] == SKILL["description"]
    path = world.zip_of(skill)
    assert path.is_file()
    package = parse_skill_package(path.read_bytes(), path.name)
    assert package["name"] == "release_notes_lookup"
    assert SKILL["procedure"] in package["procedure"]


def test_the_same_conversation_is_recalled_as_a_tool_trajectory(world):
    world.add(conversation())

    [trajectory] = [
        t for t in world.search()["tools"] if t["metadata"]["memory_type"] == "ToolTrajectoryMemory"
    ]

    assert trajectory["memory"] == TRAJECTORY[0]["trajectory"]
    assert trajectory["metadata"]["correctness"] == "success"
    assert trajectory["metadata"]["experience"] == TRAJECTORY[0]["experience"]
    assert "search_web" in json.dumps(trajectory["metadata"]["tool_used_status"])
    assert {s["role"] for s in trajectory["metadata"]["sources"]} >= {"assistant", "tool"}


def test_skills_are_recalled_per_tenant(world):
    world.add(conversation())

    other = world.search("cube-2")

    assert other == {"skills": [], "tools": []}


def test_a_second_run_of_the_same_task_updates_the_skill_in_place(world):
    world.add(conversation())
    [first] = world.search()["skills"]
    first_zip = world.zip_of(first)
    world.llm.skill = {
        **SKILL,
        "procedure": "1. Search. 2. Open the changelog. 3. Summarise.",
        "update": True,
        "old_memory_id": first["id"],
    }

    world.add(conversation())

    [second] = world.search()["skills"]
    assert second["id"] == first["id"]
    assert world.graph.count("SkillMemory") == 1
    assert "Open the changelog" in second["metadata"]["procedure"]
    assert world.zip_of(second).is_file()
    assert not first_zip.exists()
    assert len(list(first_zip.parent.glob("*.zip"))) == 1


def test_a_failed_skill_update_keeps_the_old_zip_and_leaves_no_orphan(world, monkeypatch):
    world.add(conversation())
    [first] = world.search()["skills"]
    first_zip = world.zip_of(first)
    world.llm.skill = {**SKILL, "update": True, "old_memory_id": first["id"]}

    def boom(*_a, **_k):
        raise RuntimeError("embedder down")

    monkeypatch.setattr(process_skill_memory, "create_skill_memory_item", boom)
    world.add(conversation())

    [still] = world.search()["skills"]
    assert still["metadata"]["url"] == first["metadata"]["url"]
    assert first_zip.is_file()
    assert len(list(first_zip.parent.glob("*.zip"))) == 1


def test_a_skill_update_whose_graph_write_is_lost_keeps_the_old_version_whole(world, monkeypatch):
    world.add(conversation())
    [first] = world.search()["skills"]
    first_zip = world.zip_of(first)
    world.llm.skill = {**SKILL, "update": True, "old_memory_id": first["id"]}
    monkeypatch.setattr(world.graph, "add_nodes_batch", lambda *_a, **_k: None)

    world.add(conversation())

    [still] = world.search()["skills"]
    assert still["metadata"]["url"] == first["metadata"]["url"]
    assert first_zip.is_file()
    assert len(list(first_zip.parent.glob("*.zip"))) == 1


def test_an_updated_skill_keeps_its_previous_description_in_history(world):
    world.add(conversation())
    [first] = world.search()["skills"]
    world.llm.skill = {
        **SKILL,
        "description": "Look up release notes and summarise the changelog",
        "update": True,
        "old_memory_id": first["id"],
    }

    world.add(conversation())

    props = world.graph.nodes[first["id"]]["props"]
    history = [json.loads(entry) for entry in props["history"]]
    assert (
        world.graph.nodes[first["id"]]["memory"]
        == "Look up release notes and summarise the changelog"
    )
    assert [(h["memory"], h["update_type"], h["version"]) for h in history] == [
        (SKILL["description"], "update", 1)
    ]
    assert props["version"] == 2


def test_a_skill_created_for_the_first_time_has_no_history(world):
    world.add(conversation())

    [skill] = world.search()["skills"]

    props = world.graph.nodes[skill["id"]]["props"]
    assert props["history"] == [] and props["version"] == 1


def _tool_schemas(world):
    return [
        t for t in world.search()["tools"] if t["metadata"]["memory_type"] == "ToolSchemaMemory"
    ]


def test_a_tool_schema_in_the_system_message_is_recalled_once_across_requests(world):
    world.add(conversation(with_schema=True))
    world.add(conversation(with_schema=True))

    schemas = _tool_schemas(world)

    assert [json.loads(s["memory"])["function"]["name"] for s in schemas] == ["search_web"]


def test_a_redefined_tool_keeps_one_live_schema_and_the_old_one_as_history(world):
    world.add(conversation(with_schema=True))
    function = {**SCHEMA[0]["function"], "description": "Search the web and news"}

    world.add(conversation(with_schema=True, schema=[{**SCHEMA[0], "function": function}]))

    [live] = _tool_schemas(world)
    assert json.loads(live["memory"])["function"]["description"] == "Search the web and news"
    history = [json.loads(h) for h in world.graph.nodes[live["id"]]["props"]["history"]]
    assert [json.loads(h["memory"])["function"]["description"] for h in history] == [
        "Search the web"
    ]

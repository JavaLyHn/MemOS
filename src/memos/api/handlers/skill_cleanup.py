"""Delete the skill zips behind SkillMemory nodes once their nodes are gone."""

from typing import Any, NamedTuple

from memos.log import get_logger
from memos.mem_reader.read_skill_memory import skill_store


logger = get_logger(__name__)


class SkillRef(NamedTuple):
    node_id: str
    url: str
    user_id: str


def skill_refs_from_nodes(nodes: Any, only_ids: set[str] | None = None) -> list[SkillRef]:
    """SkillMemory nodes (dicts as returned by the graph store) that carry a file URL."""
    refs: list[SkillRef] = []
    if not isinstance(nodes, list):
        return refs
    for node in nodes:
        if not isinstance(node, dict):
            continue
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        if metadata.get("memory_type") != "SkillMemory" or metadata.get("status") == "frozen":
            continue
        node_id, url, owner = node.get("id"), metadata.get("url"), metadata.get("user_id")
        if not (node_id and url and owner):
            continue
        if only_ids is not None and str(node_id) not in only_ids:
            continue
        refs.append(SkillRef(str(node_id), str(url), str(owner)))
    return refs


def skill_refs_for_file_ids(
    text_mem: Any, file_ids: list[str] | None, tenants: list[str] | None
) -> list[SkillRef]:
    """SkillMemory nodes that a ``file_ids`` delete will remove (it needs all ids on the node)."""
    graph = getattr(text_mem, "graph_store", None)
    if graph is None or not file_ids or not tenants:
        return []
    filters = [{"field": "memory_type", "op": "=", "value": "SkillMemory"}]
    filters += [{"field": "file_ids", "op": "contains", "value": [f]} for f in file_ids]
    try:
        node_ids = graph.get_by_metadata(filters=filters, knowledgebase_ids=list(tenants))
        if not isinstance(node_ids, list) or not node_ids:
            return []
        return skill_refs_from_nodes(text_mem.get_by_ids(node_ids))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[SKILL_CLEANUP] could not enumerate skills for file_ids %s: %s", file_ids, e
        )
        return []


def _oss_client() -> Any:
    from memos.api.config import APIConfig
    from memos.mem_reader.read_skill_memory.process_skill_memory import create_oss_client

    return create_oss_client(APIConfig.get_oss_config())


def delete_skill_files(text_mem: Any, refs: list[SkillRef]) -> int:
    """Delete files for refs whose nodes are really gone. Never raises."""
    if not refs:
        return 0
    try:
        remaining = text_mem.get_by_ids([r.node_id for r in refs])
        if not isinstance(remaining, list):
            return 0
        survivors = {str(n.get("id")) for n in remaining if isinstance(n, dict)}
    except Exception as e:  # noqa: BLE001
        logger.warning("[SKILL_CLEANUP] could not confirm node deletion, keeping files: %s", e)
        return 0

    backend = skill_store.storage_backend()
    config = skill_store.skills_dir_config_from_env()
    client = None
    deleted = 0
    for ref in refs:
        if ref.node_id in survivors:
            continue
        try:
            if backend == "OSS" and client is None:
                client = _oss_client()
            if skill_store.delete_skill_by_url(
                ref.url, ref.user_id, backend=backend, skills_dir_config=config, oss_client=client
            ):
                deleted += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[SKILL_CLEANUP] failed to delete skill file %s: %s", ref.url, e)
    return deleted

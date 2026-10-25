"""
Memory handler for retrieving and managing memories.

This module handles retrieving all memories or specific subgraphs based on queries.
"""

from typing import Any, Literal

from fastapi import HTTPException

from memos.api.handlers.skill_cleanup import (
    delete_skill_files,
    skill_refs_for_file_ids,
    skill_refs_from_nodes,
)
from memos.api.product_models import (
    DeleteMemoryRequest,
    DeleteMemoryResponse,
    GetEventMemoriesRequest,
    GetEventMemoriesResponse,
    GetMemoryDashboardRequest,
    GetMemoryGraphRequest,
    GetMemoryGraphResponse,
    GetMemoryRequest,
    GetMemoryResponse,
    MemoryResponse,
)
from memos.log import get_logger
from memos.mem_cube.navie import NaiveMemCube
from memos.mem_os.utils.format_utils import (
    convert_graph_to_tree_forworkmem,
    ensure_unique_tree_ids,
    filter_nodes_by_tree_ids,
    remove_embedding_recursive,
    sort_children_by_memory_type,
)


logger = get_logger(__name__)

# The list shows what the owner can still act on; archived (superseded) and deleted nodes are history.
LISTED_STATUSES = ["activated", "resolving", "frozen", "expired"]


def _with_skill_url(node: Any) -> Any:
    """A skill node always carries ``metadata.url``: empty when its file was never stored."""
    metadata = node.get("metadata") if isinstance(node, dict) else None
    is_skill = isinstance(metadata, dict) and metadata.get("memory_type") == "SkillMemory"
    if is_skill and metadata.get("url") is None:
        return {**node, "metadata": {**metadata, "url": ""}}
    return node


def handle_get_all_memories(
    user_id: str,
    mem_cube_id: str,
    memory_type: Literal["text_mem", "act_mem", "param_mem", "para_mem"],
    naive_mem_cube: Any,
) -> MemoryResponse:
    """
    Main handler for getting all memories.

    Retrieves all memories of specified type for a user and formats them appropriately.

    Args:
        user_id: User ID
        mem_cube_id: Memory cube ID
        memory_type: Type of memory to retrieve
        naive_mem_cube: Memory cube instance

    Returns:
        MemoryResponse with formatted memory data
    """
    try:
        reformat_memory_list = []

        if memory_type == "text_mem":
            # Get all text memories from the graph database
            memories = naive_mem_cube.text_mem.get_all(user_name=mem_cube_id)

            # Format and convert to tree structure
            memories_cleaned = remove_embedding_recursive(memories)
            custom_type_ratios = {
                "WorkingMemory": 0.20,
                "LongTermMemory": 0.40,
                "UserMemory": 0.40,
            }
            tree_result, node_type_count = convert_graph_to_tree_forworkmem(
                memories_cleaned, target_node_count=200, type_ratios=custom_type_ratios
            )
            # Ensure all node IDs are unique in the tree structure
            tree_result = ensure_unique_tree_ids(tree_result)
            memories_filtered = filter_nodes_by_tree_ids(tree_result, memories_cleaned)
            children = tree_result["children"]
            children_sort = sort_children_by_memory_type(children)
            tree_result["children"] = children_sort
            memories_filtered["tree_structure"] = tree_result

            reformat_memory_list.append(
                {
                    "cube_id": mem_cube_id,
                    "memories": [memories_filtered],
                    "memory_statistics": node_type_count,
                }
            )

        elif memory_type == "act_mem":
            logger.warning("Activity memory retrieval not implemented yet.")
        elif memory_type == "para_mem":
            logger.warning("Parameter memory retrieval not implemented yet.")
        return MemoryResponse(
            message="Memories retrieved successfully",
            data=reformat_memory_list,
        )

    except Exception as e:
        logger.error(f"Failed to get all memories: {e}", exc_info=True)
        raise


def handle_get_subgraph(
    user_id: str,
    mem_cube_id: str,
    query: str,
    top_k: int,
    naive_mem_cube: Any,
    search_type: Literal["embedding", "fulltext"],
) -> MemoryResponse:
    """
    Main handler for getting memory subgraph based on query.

    Retrieves relevant memory subgraph and formats it as a tree structure.

    Args:
        user_id: User ID
        mem_cube_id: Memory cube ID
        query: Search query
        top_k: Number of top results to return
        naive_mem_cube: Memory cube instance

    Returns:
        MemoryResponse with formatted subgraph data
    """
    try:
        # Get relevant subgraph from text memory
        memories = naive_mem_cube.text_mem.get_relevant_subgraph(
            query, top_k=top_k, user_name=mem_cube_id, search_type=search_type
        )

        # Format and convert to tree structure
        memories_cleaned = remove_embedding_recursive(memories)
        custom_type_ratios = {
            "WorkingMemory": 0.20,
            "LongTermMemory": 0.40,
            "UserMemory": 0.40,
        }
        tree_result, node_type_count = convert_graph_to_tree_forworkmem(
            memories_cleaned, target_node_count=200, type_ratios=custom_type_ratios
        )
        # Ensure all node IDs are unique in the tree structure
        tree_result = ensure_unique_tree_ids(tree_result)
        memories_filtered = filter_nodes_by_tree_ids(tree_result, memories_cleaned)
        children = tree_result["children"]
        children_sort = sort_children_by_memory_type(children)
        tree_result["children"] = children_sort
        memories_filtered["tree_structure"] = tree_result

        reformat_memory_list = [
            {
                "cube_id": mem_cube_id,
                "memories": [memories_filtered],
                "memory_statistics": node_type_count,
            }
        ]

        return MemoryResponse(
            message="Memories retrieved successfully",
            data=reformat_memory_list,
        )

    except Exception as e:
        logger.error(f"Failed to get subgraph: {e}", exc_info=True)
        raise


def handle_get_memory(
    memory_id: str, naive_mem_cube: NaiveMemCube, mem_cube_id: str | None = None
) -> GetMemoryResponse:
    """
    Handler for getting a single memory by its ID.
    Now unified to retrieve from text_mem only (includes preferences).

    Args:
        memory_id: The ID of the memory to retrieve
        naive_mem_cube: Memory cube instance
        mem_cube_id: When given, the memory must belong to this cube; otherwise the id is
            looked up across cubes, which is how callers find a memory's owner.

    Returns:
        GetMemoryResponse with the memory data
    """

    try:
        memory = naive_mem_cube.text_mem.get(memory_id, user_name=mem_cube_id)
    except Exception as e:
        logger.error(f"Failed to get memory {memory_id}: {e}")
        memory = None

    # Get the data
    data = _with_skill_url(memory.model_dump()) if memory else None

    return GetMemoryResponse(
        message="Memory retrieved successfully"
        if data
        else f"Memory with ID {memory_id} not found",
        code=200,
        data=data,
    )


def handle_get_memory_by_ids(
    memory_ids: list[str], naive_mem_cube: NaiveMemCube, mem_cube_id: str | None = None
) -> GetMemoryResponse:
    """
    Handler for getting multiple memories by their IDs.
    Now unified to retrieve from text_mem only (includes preferences).

    Retrieves multiple memories and formats them as a list of dictionaries. ``mem_cube_id``
    names the cube the ids must belong to; without it the service's default cube is used.
    """
    try:
        memories = naive_mem_cube.text_mem.get_by_ids(memory_ids=memory_ids, user_name=mem_cube_id)
    except Exception as e:
        logger.error(f"Failed to get memories: {e}")
        memories = []

    # Ensure memories is not None
    if memories is None:
        memories = []

    return GetMemoryResponse(
        message="Memories retrieved successfully",
        code=200,
        data={"memories": [_with_skill_url(memory) for memory in memories]},
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _graph_node_json(node: dict[str, Any], label_max: int | None) -> dict[str, Any]:
    """Project a graph-store node into the dashboard's stable field names.

    ``label_max`` truncates only the label; the full body stays available through
    ``GET /product/get_memory/{id}``.
    """
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    memory = str(node.get("memory") or "")
    truncated = label_max is not None and len(memory) > label_max
    label = f"{memory[:label_max]}…" if truncated else memory
    source_ids = _string_list(metadata.get("source_memory_ids"))
    if not source_ids:
        source_ids = _string_list(metadata.get("merged_from"))
    return {
        "id": str(node.get("id") or ""),
        "memory": label,
        "memoryTruncated": truncated,
        "memoryType": str(metadata.get("memory_type") or ""),
        "status": str(metadata.get("status") or ""),
        "createdAt": _iso(metadata.get("created_at")),
        "updatedAt": _iso(metadata.get("updated_at")),
        # Carried through so the API boundary can tell real-UTC nodes from
        # legacy Beijing wall-clock ones (see memos.time_basis).
        "time_basis": str(metadata.get("time_basis") or ""),
        "sessionId": str(metadata.get("session_id") or ""),
        "userId": str(metadata.get("user_id") or ""),
        "sourceMemoryIds": source_ids,
    }


def _type_stats(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for node in nodes:
        name = node["memoryType"] or "Unknown"
        counts[name] = counts.get(name, 0) + 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def handle_get_memory_graph(
    get_graph_req: GetMemoryGraphRequest, naive_mem_cube: NaiveMemCube
) -> GetMemoryGraphResponse:
    """Return the dashboard graph view without exposing the graph backend.

    Nodes and edges come from the same tenant-scoped export call. Edges whose
    endpoints fall outside the returned node page are dropped, because a client
    cannot draw a dangling edge.
    """
    exported = naive_mem_cube.text_mem.get_all(
        user_name=get_graph_req.mem_cube_id,
        page=1,
        page_size=get_graph_req.limit,
        memory_type=get_graph_req.memory_types,
        status=get_graph_req.status,
    )
    raw_nodes = exported.get("nodes") or []
    nodes = [_graph_node_json(node, get_graph_req.label_max) for node in raw_nodes]
    node_ids = {node["id"] for node in nodes}

    edges: list[dict[str, str]] = []
    if get_graph_req.include_edges:
        for edge in exported.get("edges") or []:
            kind = str(edge.get("type") or "").upper()
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if kind not in {"PARENT", "MERGED_TO"}:
                continue
            if source not in node_ids or target not in node_ids:
                continue
            edges.append({"source": source, "target": target, "type": kind})

    total_nodes = int(exported.get("total_nodes") or len(nodes))
    return GetMemoryGraphResponse(
        message="Memory graph retrieved successfully",
        data={
            "cube_id": get_graph_req.mem_cube_id,
            "nodes": nodes,
            "edges": edges,
            "total_nodes": total_nodes,
            "total_edges": len(edges),
            "truncated": total_nodes > len(nodes),
            "stats": {"types": _type_stats(nodes)},
        },
    )


def handle_get_event_memories(
    get_event_req: GetEventMemoriesRequest, naive_mem_cube: NaiveMemCube
) -> GetEventMemoriesResponse:
    """List event and Dream memories with real pagination and an optional text filter."""
    filter_ = (
        {"memory": {"like": get_event_req.search_query}} if get_event_req.search_query else None
    )
    get_all_kwargs: dict[str, Any] = {
        "user_name": get_event_req.mem_cube_id,
        "page": get_event_req.page,
        "page_size": get_event_req.page_size,
        "filter": filter_,
        "memory_type": get_event_req.memory_types or None,
    }
    if get_event_req.status:
        get_all_kwargs["status"] = get_event_req.status
    exported = naive_mem_cube.text_mem.get_all(**get_all_kwargs)
    memories = [_graph_node_json(node, None) for node in (exported.get("nodes") or [])]
    total = int(exported.get("total_nodes") or len(memories))
    return GetEventMemoriesResponse(
        message="Event memories retrieved successfully",
        data={
            "cube_id": get_event_req.mem_cube_id,
            "memories": memories,
            "total": total,
            "page": get_event_req.page,
            "page_size": get_event_req.page_size,
        },
    )


def _agent_filter(
    filter_: dict[str, Any] | None, agent_id: str | list[str] | None
) -> dict[str, Any] | None:
    """Narrow a list query to memories related to the given agents."""
    from memos.memories.textual.owner import normalize_id_list

    ids = normalize_id_list(agent_id)
    if not ids:
        return filter_
    merged = dict(filter_ or {})
    if "agent_id" not in merged:
        merged["agent_id"] = {"in": ids} if len(ids) > 1 else ids[0]
    return merged


def _profile_bucket(
    naive_mem_cube: NaiveMemCube, get_mem_req: GetMemoryRequest
) -> list[dict[str, Any]]:
    from memos.api.cloud_store import build_metadata_store
    from memos.api.profile import ProfileService
    from memos.memories.textual.owner import normalize_id_list

    graph_store = getattr(naive_mem_cube.text_mem, "graph_store", None)
    if graph_store is None:
        return []
    try:
        service = ProfileService(build_metadata_store(graph_store))
        subjects: list[dict[str, str]] = []
        if get_mem_req.user_id:
            subjects.append({"user_id": get_mem_req.user_id})
        subjects.extend({"agent_id": aid} for aid in normalize_id_list(get_mem_req.agent_id))
        memories = [
            memory
            for subject in subjects
            for memory in service.recall(user_name=get_mem_req.mem_cube_id, **subject)
        ]
    except Exception:
        logger.warning("Profile listing unavailable", exc_info=True)
        return []
    if not memories:
        return []
    return [
        {"cube_id": get_mem_req.mem_cube_id, "memories": memories, "total_nodes": len(memories)}
    ]


def handle_get_memories(
    get_mem_req: GetMemoryRequest, naive_mem_cube: NaiveMemCube
) -> GetMemoryResponse:
    if not get_mem_req.mem_cube_id:
        return GetMemoryResponse(message="mem_cube_id or user_id is required", code=400, data=None)

    detail_types = ["WorkingMemory", "LongTermMemory", "UserMemory", "OuterMemory"]
    views = get_mem_req.include_memory_view
    filter_ = _agent_filter(get_mem_req.filter, get_mem_req.agent_id)

    def bucket(memories: list[dict[str, Any]], total: int) -> list[dict[str, Any]]:
        return [{"cube_id": get_mem_req.mem_cube_id, "memories": memories, "total_nodes": total}]

    def list_of(memory_type: list[str]) -> tuple[list[dict[str, Any]], int]:
        info = naive_mem_cube.text_mem.get_all(
            user_name=get_mem_req.mem_cube_id,
            user_id=get_mem_req.user_id,
            page=get_mem_req.page,
            page_size=get_mem_req.page_size,
            filter=filter_,
            memory_type=memory_type,
            status=LISTED_STATUSES,
        )
        return info["nodes"], info["total_nodes"]

    results: dict[str, Any] = {}
    if views is None:
        # Legacy shape: events stay in text_mem and there is no profile bucket.
        memories, total = list_of([*detail_types, "EventMemory"])
        results["text_mem"] = bucket(memories, total)
    else:
        if "detail_factual" in views:
            results["text_mem"] = bucket(*list_of(detail_types))
        if "event" in views:
            results["event_mem"] = bucket(*list_of(["EventMemory"]))

    if get_mem_req.include_tool_memory:
        memories, total = list_of(["ToolSchemaMemory", "ToolTrajectoryMemory"])
        results["tool_mem"] = bucket(memories, total)
    if get_mem_req.include_skill_memory:
        memories, total = list_of(["SkillMemory"])
        results["skill_mem"] = bucket([_with_skill_url(node) for node in memories], total)
    if get_mem_req.include_preference:
        results["pref_mem"] = bucket(*list_of(["PreferenceMemory"]))
    if views is not None and "profile" in views:
        profiles = _profile_bucket(naive_mem_cube, get_mem_req)
        if profiles:
            results["profile_mem"] = profiles

    return GetMemoryResponse(message="Memories retrieved successfully", data=results)


def _build_quick_delete_constraints(delete_mem_req: DeleteMemoryRequest) -> dict[str, Any]:
    """Build graph-node constraints; the tenant is stored as ``user_name``."""
    constraints: dict[str, Any] = {}
    if delete_mem_req.writable_cube_ids:
        # Memories are written with the cube id as ``user_name``; a request that
        # names cubes must match those, not the caller's user_id.
        constraints["user_name"] = {"in": list(dict.fromkeys(delete_mem_req.writable_cube_ids))}
    elif delete_mem_req.user_id is not None:
        constraints["user_name"] = delete_mem_req.user_id
    if delete_mem_req.agent_id is not None:
        # Only nodes the agent owns: user views also store ``agent_id`` as a
        # compatibility property, and those belong to the user.
        constraints["owner_type"] = "agent"
        constraints["owner_id"] = delete_mem_req.agent_id
    if delete_mem_req.session_id is not None:
        constraints["session_id"] = delete_mem_req.session_id
    return constraints


def _build_pref_delete_constraints(delete_mem_req: DeleteMemoryRequest) -> dict[str, Any]:
    """Preference vectors store the same tenant as ``user_id``, not ``user_name``."""
    constraints: dict[str, Any] = {}
    if delete_mem_req.user_id is not None:
        constraints["user_id"] = delete_mem_req.user_id
    if delete_mem_req.session_id is not None:
        constraints["session_id"] = delete_mem_req.session_id
    return constraints


def _merge_delete_filter(
    base_filter: dict[str, Any] | None,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Merge user/session constraints into an existing filter."""
    if not constraints:
        return base_filter or {}
    if base_filter is None:
        return {"and": [constraints.copy()]}

    if not base_filter:
        return {"and": [constraints.copy()]}

    if "and" in base_filter:
        and_conditions = base_filter.get("and")
        if not isinstance(and_conditions, list):
            raise ValueError("Invalid filter format: 'and' must be a list")
        return {"and": [*and_conditions, constraints.copy()]}

    if "or" in base_filter:
        or_conditions = base_filter.get("or")
        if not isinstance(or_conditions, list):
            raise ValueError("Invalid filter format: 'or' must be a list")

        merged_or_conditions: list[dict[str, Any]] = []
        for condition in or_conditions:
            if not isinstance(condition, dict):
                raise ValueError("Invalid filter format: each 'or' condition must be a dict")
            merged_condition = condition.copy()
            for key, value in constraints.items():
                if key in merged_condition and merged_condition[key] != value:
                    raise ValueError(
                        f"Conflicting filter condition for '{key}'. "
                        "Please merge it manually into request.filter."
                    )
                merged_condition[key] = value
            merged_or_conditions.append(merged_condition)

        return {"or": merged_or_conditions}

    # For plain dict filters, keep strict AND semantics explicitly.
    return {"and": [base_filter.copy(), constraints.copy()]}


def _frozen_ids(nodes: list[Any]) -> list[str]:
    """Ids of frozen memories among exported graph nodes."""
    frozen: list[str] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        if metadata.get("status") == "frozen" or node.get("status") == "frozen":
            frozen.append(str(node.get("id")))
    return frozen


def _delete_by_filter_preserving_frozen(
    text_mem: Any,
    filter: dict[str, Any],
    tenants: list[str],
    skill_refs: list[Any] | None = None,
) -> bool:
    """Delete by filter while keeping frozen (compliance-locked) nodes.

    Returns True when the guard ran; False when the store cannot enumerate
    matches (then the caller falls back to a plain filter delete — the graph
    layer still refuses to delete ``frozen`` nodes). Raises when enumeration
    fails, so the caller can reject the delete instead of silently unlinking
    nodes it could not inspect.
    """
    if not tenants:
        return False

    graph_store = getattr(text_mem, "graph_store", None)
    get_all = getattr(text_mem, "get_all", None)

    nodes: list[dict[str, Any]] = []
    for tenant in tenants:
        exported = None
        if graph_store is not None and hasattr(graph_store, "export_graph"):
            try:
                # status=[] means "no status constraint", so soft-deleted nodes
                # are included too (the historical filter delete removed them).
                exported = graph_store.export_graph(
                    user_name=tenant, filter=filter, page_size=None, status=[]
                )
            except TypeError:
                exported = None  # backend without a status parameter
        if exported is None:
            if not callable(get_all):
                return False
            exported = get_all(user_name=tenant, filter=filter, page_size=None)
        if not isinstance(exported, dict):
            return False
        nodes.extend(exported.get("nodes") or [])

    frozen = set(_frozen_ids(nodes))
    deletable = [
        str(node.get("id"))
        for node in nodes
        if isinstance(node, dict) and node.get("id") and str(node.get("id")) not in frozen
    ]
    if frozen:
        logger.warning(
            "Skipping %d frozen memories during delete: %s", len(frozen), sorted(frozen)[:10]
        )
    if skill_refs is not None:
        skill_refs.extend(skill_refs_from_nodes(nodes, only_ids=set(deletable)))
    if deletable:
        text_mem.delete_by_memory_ids(list(dict.fromkeys(deletable)))
    return True


def _message_purge_scope(
    delete_mem_req: DeleteMemoryRequest,
) -> tuple[list[str] | None, str | None] | None:
    """Tenants and conversation whose raw messages go with a whole-user/session delete.

    A session-only delete names no tenant, exactly like the memory side, which then
    matches the session across tenants; the messages follow the same rule.
    """
    if (
        delete_mem_req.memory_ids is not None
        or delete_mem_req.file_ids is not None
        or delete_mem_req.filter
        or delete_mem_req.agent_id is not None
    ):
        return None
    tenants = list(dict.fromkeys(delete_mem_req.writable_cube_ids or [])) or (
        [delete_mem_req.user_id] if delete_mem_req.user_id else []
    )
    if tenants:
        return tenants, delete_mem_req.session_id
    return (None, delete_mem_req.session_id) if delete_mem_req.session_id else None


def handle_delete_memories(
    delete_mem_req: DeleteMemoryRequest,
    naive_mem_cube: NaiveMemCube,
    message_store: Any = None,
):
    """
    Handler for deleting memories.
    Now unified to delete from text_mem only (includes preferences).
    """
    logger.info(
        "[Delete memory request] writable_cube_ids: %s, memory_ids: %s, file_ids: %s, "
        "auto_cleanup_working: %s, has_filter: %s, user_id: %s, agent_id: %s, session_id: %s",
        delete_mem_req.writable_cube_ids,
        delete_mem_req.memory_ids,
        delete_mem_req.file_ids,
        getattr(delete_mem_req, "auto_cleanup_working", False),
        delete_mem_req.filter is not None,
        delete_mem_req.user_id,
        delete_mem_req.agent_id,
        delete_mem_req.session_id,
    )
    quick_constraints = _build_quick_delete_constraints(delete_mem_req)
    has_non_empty_filter = bool(delete_mem_req.filter)
    # With file_ids / memory_ids the cubes only scope the delete (the graph store
    # requires them); they are not a second delete mode.
    cubes_only_scope = (
        (delete_mem_req.memory_ids is not None or delete_mem_req.file_ids is not None)
        and bool(delete_mem_req.writable_cube_ids)
        and set(quick_constraints) <= {"user_name"}
    )
    has_filter_mode = has_non_empty_filter or (bool(quick_constraints) and not cubes_only_scope)

    # An agent is not a tenant: without a cube or user_id there is no tenant
    # boundary, so refuse instead of deleting that agent id across tenants.
    if delete_mem_req.agent_id is not None and "user_name" not in quick_constraints:
        raise HTTPException(
            status_code=400,
            detail="agent_id delete requires writable_cube_ids or user_id to name the tenant.",
        )

    # Reject empty filter dict when no quick constraints are provided.
    if delete_mem_req.filter is not None and not has_non_empty_filter and not quick_constraints:
        raise HTTPException(
            status_code=400,
            detail="filter cannot be empty; provide a non-empty filter or user_id/session_id.",
        )

    # Validate that only one mode is provided: memory_ids, file_ids, or filter-mode.
    provided_params = [
        delete_mem_req.memory_ids is not None,
        delete_mem_req.file_ids is not None,
        has_filter_mode,
    ]
    if sum(provided_params) != 1:
        # A malformed request is a client error; 200 + data.status=failure made
        # callers believe the delete succeeded. See docs/api-contract.md.
        raise HTTPException(
            status_code=400,
            detail=(
                "Exactly one delete mode must be provided: "
                "memory_ids, file_ids, or filter/user_id/session_id."
            ),
        )

    skill_refs: list[Any] = []
    delete_scope: list[str] | None = None
    try:
        working_ids_to_delete: set[str] = set()
        # When deleting by explicit memory_ids and auto_cleanup_working is enabled,
        # collect related WorkingMemory ids from working_binding
        if delete_mem_req.memory_ids is not None and getattr(
            delete_mem_req, "auto_cleanup_working", False
        ):
            try:
                memories = naive_mem_cube.text_mem.get_by_ids(memory_ids=delete_mem_req.memory_ids)
            except Exception as e:
                logger.warning("Failed to fetch memories before delete for working cleanup: %s", e)
                memories = []

            if memories:
                import re

                pattern = re.compile(r"\[working_binding:([0-9a-fA-F-]{36})\]")
                for mem in memories:
                    metadata = mem.get("metadata") or {}
                    bg = metadata.get("background") or ""
                    if not isinstance(bg, str):
                        continue
                    match = pattern.search(bg)
                    if match:
                        working_ids_to_delete.add(match.group(1))

        if delete_mem_req.memory_ids is not None:
            # Frozen memories are compliance-locked: reject the request rather
            # than silently deleting the rest.
            try:
                selected = naive_mem_cube.text_mem.get_by_ids(memory_ids=delete_mem_req.memory_ids)
            except Exception:
                logger.error("Could not verify frozen state before delete", exc_info=True)
                return DeleteMemoryResponse(
                    message="delete aborted: could not verify frozen memories",
                    code=500,
                    data={"status": "failure"},
                )
            if isinstance(selected, list):
                frozen = _frozen_ids(selected)
                if frozen:
                    return DeleteMemoryResponse(
                        message=(
                            "memory is frozen (compliance lock) and cannot be deleted: "
                            f"{frozen[:10]}"
                        ),
                        data={"status": "failure", "frozen_memory_ids": frozen},
                    )
                skill_refs = skill_refs_from_nodes(selected)
            # Unified deletion from text_mem (includes preferences).
            # 共享图库必须带租户作用域: 请求没给 writable_cube_ids 时退回当前
            # cube 的 id; 两者都没有则拒绝,避免只凭 id 删到别的租户。
            delete_scope = delete_mem_req.writable_cube_ids
            if not delete_scope:
                cube_id = getattr(
                    getattr(naive_mem_cube.text_mem, "config", None), "cube_id", None
                )
                delete_scope = [cube_id] if cube_id else None
            if not delete_scope:
                return DeleteMemoryResponse(
                    message=(
                        "writable_cube_ids is required when deleting by memory_ids "
                        "(no cube_id on the current memory store)"
                    ),
                    data={"status": "failure"},
                )
            naive_mem_cube.text_mem.delete_by_memory_ids(
                delete_mem_req.memory_ids, writable_cube_ids=delete_scope
            )
        elif delete_mem_req.file_ids is not None:
            skill_refs = skill_refs_for_file_ids(
                naive_mem_cube.text_mem, delete_mem_req.file_ids, delete_mem_req.writable_cube_ids
            )
            naive_mem_cube.text_mem.delete_by_filter(
                writable_cube_ids=delete_mem_req.writable_cube_ids, file_ids=delete_mem_req.file_ids
            )
        elif has_filter_mode:
            merged_filter = _merge_delete_filter(delete_mem_req.filter, quick_constraints)
            guard_tenants = list(dict.fromkeys(delete_mem_req.writable_cube_ids or [])) or (
                [delete_mem_req.user_id] if delete_mem_req.user_id else []
            )
            try:
                guarded = _delete_by_filter_preserving_frozen(
                    naive_mem_cube.text_mem, merged_filter, guard_tenants, skill_refs
                )
            except Exception:
                logger.error("Could not verify frozen memories before delete", exc_info=True)
                return DeleteMemoryResponse(
                    message=(
                        "delete aborted: could not verify frozen memories; "
                        "retry or delete by memory_ids"
                    ),
                    code=500,
                    data={"status": "failure"},
                )
            if not guarded:
                naive_mem_cube.text_mem.delete_by_filter(
                    writable_cube_ids=delete_mem_req.writable_cube_ids,
                    filter=merged_filter,
                )
            # Agent deletes stay in the graph: preference vectors are keyed by the
            # tenant ``user_id``, so a user-keyed filter here would wipe the
            # user's own preferences.
            if naive_mem_cube.pref_mem is not None and delete_mem_req.agent_id is None:
                pref_filter = _merge_delete_filter(
                    delete_mem_req.filter, _build_pref_delete_constraints(delete_mem_req)
                )
                naive_mem_cube.pref_mem.delete_by_filter(filter=pref_filter)

        delete_skill_files(naive_mem_cube.text_mem, skill_refs)

        purge_scope = _message_purge_scope(delete_mem_req)
        if message_store is not None and purge_scope is not None:
            # Retry-safe: the memories above are already gone, so a failure here must
            # surface instead of leaving the raw text behind a success reply.
            try:
                message_store.delete(user_names=purge_scope[0], conversation_id=purge_scope[1])
            except Exception:
                logger.exception("Failed to delete raw messages")
                return DeleteMemoryResponse(
                    message="memories deleted but raw messages could not be removed; retry",
                    code=500,
                    data={"status": "failure"},
                )

        # After main deletion, optionally clean up related WorkingMemory nodes.
        if working_ids_to_delete:
            try:
                logger.info(
                    "Auto-cleanup WorkingMemory nodes after delete, count=%d",
                    len(working_ids_to_delete),
                )
                naive_mem_cube.text_mem.delete_by_memory_ids(
                    list(working_ids_to_delete), writable_cube_ids=delete_scope
                )
            except Exception as e:
                logger.warning("Failed to auto-cleanup WorkingMemory nodes: %s, Pass", e)
    except Exception as e:
        logger.error(f"Failed to delete memories: {e}", exc_info=True)
        return DeleteMemoryResponse(
            message="Failed to delete memories",
            data={"status": "failure"},
        )
    return DeleteMemoryResponse(
        message="Memories deleted successfully",
        data={"status": "success"},
    )


# =============================================================================
# Other handler functions Endpoints (for internal use)
# =============================================================================


def handle_get_memories_dashboard(
    get_mem_req: GetMemoryDashboardRequest, naive_mem_cube: NaiveMemCube
) -> GetMemoryResponse:
    results: dict[str, Any] = {"text_mem": [], "pref_mem": [], "tool_mem": [], "skill_mem": []}
    # for statistics
    total_text_nodes, total_tool_nodes, total_skill_nodes, total_preference_nodes = 0, 0, 0, 0
    total_tool_nodes = 0
    total_skill_nodes = 0
    total_preference_nodes = 0

    text_memory_type = [
        "WorkingMemory",
        "LongTermMemory",
        "UserMemory",
        "OuterMemory",
        "EventMemory",
    ]
    text_memories_info = naive_mem_cube.text_mem.get_all(
        user_name=get_mem_req.mem_cube_id,
        user_id=get_mem_req.user_id,
        page=get_mem_req.page,
        page_size=get_mem_req.page_size,
        filter=get_mem_req.filter,
        memory_type=text_memory_type,
    )
    text_memories, total_text_nodes = text_memories_info["nodes"], text_memories_info["total_nodes"]

    # Group text memories by cube_id from metadata.user_name
    text_mem_by_cube: dict[str, list] = {}
    for memory in text_memories:
        cube_id = memory.get("metadata", {}).get("user_name", get_mem_req.mem_cube_id)
        if cube_id not in text_mem_by_cube:
            text_mem_by_cube[cube_id] = []
        text_mem_by_cube[cube_id].append(memory)

    # If no memories found, create a default entry with the requested cube_id
    if not text_mem_by_cube and get_mem_req.mem_cube_id:
        text_mem_by_cube[get_mem_req.mem_cube_id] = []

    results["text_mem"] = [
        {
            "cube_id": cube_id,
            "memories": memories,
            "total_nodes": len(memories),
        }
        for cube_id, memories in text_mem_by_cube.items()
    ]

    if get_mem_req.include_tool_memory:
        tool_memories_info = naive_mem_cube.text_mem.get_all(
            user_name=get_mem_req.mem_cube_id,
            user_id=get_mem_req.user_id,
            page=get_mem_req.page,
            page_size=get_mem_req.page_size,
            filter=get_mem_req.filter,
            memory_type=["ToolSchemaMemory", "ToolTrajectoryMemory"],
        )
        tool_memories, total_tool_nodes = (
            tool_memories_info["nodes"],
            tool_memories_info["total_nodes"],
        )

        # Group tool memories by cube_id from metadata.user_name
        tool_mem_by_cube: dict[str, list] = {}
        for memory in tool_memories:
            cube_id = memory.get("metadata", {}).get("user_name", get_mem_req.mem_cube_id)
            if cube_id not in tool_mem_by_cube:
                tool_mem_by_cube[cube_id] = []
            tool_mem_by_cube[cube_id].append(memory)

        # If no memories found, create a default entry with the requested cube_id
        if not tool_mem_by_cube and get_mem_req.mem_cube_id:
            tool_mem_by_cube[get_mem_req.mem_cube_id] = []

        results["tool_mem"] = [
            {
                "cube_id": cube_id,
                "memories": memories,
                "total_nodes": len(memories),
            }
            for cube_id, memories in tool_mem_by_cube.items()
        ]

    if get_mem_req.include_skill_memory:
        skill_memories_info = naive_mem_cube.text_mem.get_all(
            user_name=get_mem_req.mem_cube_id,
            user_id=get_mem_req.user_id,
            page=get_mem_req.page,
            page_size=get_mem_req.page_size,
            filter=get_mem_req.filter,
            memory_type=["SkillMemory"],
        )
        skill_memories, total_skill_nodes = (
            skill_memories_info["nodes"],
            skill_memories_info["total_nodes"],
        )

        # Group skill memories by cube_id from metadata.user_name
        skill_mem_by_cube: dict[str, list] = {}
        for memory in skill_memories:
            cube_id = memory.get("metadata", {}).get("user_name", get_mem_req.mem_cube_id)
            if cube_id not in skill_mem_by_cube:
                skill_mem_by_cube[cube_id] = []
            skill_mem_by_cube[cube_id].append(memory)

        # If no memories found, create a default entry with the requested cube_id
        if not skill_mem_by_cube and get_mem_req.mem_cube_id:
            skill_mem_by_cube[get_mem_req.mem_cube_id] = []

        results["skill_mem"] = [
            {
                "cube_id": cube_id,
                "memories": memories,
                "total_nodes": len(memories),
            }
            for cube_id, memories in skill_mem_by_cube.items()
        ]

    if get_mem_req.include_preference:
        pref_memories_info = naive_mem_cube.text_mem.get_all(
            user_name=get_mem_req.mem_cube_id,
            user_id=get_mem_req.user_id,
            page=get_mem_req.page,
            page_size=get_mem_req.page_size,
            filter=get_mem_req.filter,
            memory_type=["PreferenceMemory"],
        )
        pref_memories, total_preference_nodes = (
            pref_memories_info["nodes"],
            pref_memories_info["total_nodes"],
        )

        # Group preference memories by cube_id from metadata.user_name
        pref_mem_by_cube: dict[str, list] = {}
        for memory in pref_memories:
            cube_id = memory.get("metadata", {}).get("user_name", get_mem_req.mem_cube_id)
            if cube_id not in pref_mem_by_cube:
                pref_mem_by_cube[cube_id] = []
            pref_mem_by_cube[cube_id].append(memory)

        # If no memories found, create a default entry with the requested cube_id
        if not pref_mem_by_cube and get_mem_req.mem_cube_id:
            pref_mem_by_cube[get_mem_req.mem_cube_id] = []

        results["pref_mem"] = [
            {
                "cube_id": cube_id,
                "memories": memories,
                "total_nodes": len(memories),
            }
            for cube_id, memories in pref_mem_by_cube.items()
        ]

    # Filter to only keep text_mem, pref_mem, tool_mem, skill_mem
    filtered_results = {
        "text_mem": results.get("text_mem", []),
        "pref_mem": results.get("pref_mem", []),
        "tool_mem": results.get("tool_mem", []),
        "skill_mem": results.get("skill_mem", []),
    }

    # statistics
    statistics = {
        "total_text_nodes": total_text_nodes,
        "total_tool_nodes": total_tool_nodes,
        "total_skill_nodes": total_skill_nodes,
        "total_preference_nodes": total_preference_nodes,
    }
    filtered_results["statistics"] = statistics

    return GetMemoryResponse(message="Memories retrieved successfully", data=filtered_results)

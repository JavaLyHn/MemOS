"""HugeGraph backend for MemOS using the official hugegraph-python client."""

import json
import re

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Literal

from memos.configs.graph_db import HugeGraphDBConfig
from memos.dependency import require_python_package
from memos.graph_dbs.base import BaseGraphDB
from memos.log import get_logger
from memos.vec_dbs.index import BaseVectorIndex, VectorIndexFactory
from memos.vec_dbs.item import VecDBItem


logger = get_logger(__name__)

_VERTEX_LABEL = "Memory"
_EDGE_LABEL = "MEMORY_RELATION"
_RELATION_TYPE_KEY = "relation_type"
_VALID_PROPERTY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _pack_metadata(metadata: dict[str, Any]) -> str:
    reserved = {
        "memory_type",
        "status",
        "user_name",
        "embedding",
        "created_at",
        "updated_at",
        "mem_cube_id",
        "delete_record_id",
        "delete_time",
    }
    return json.dumps(
        {k: v for k, v in metadata.items() if k not in reserved}, ensure_ascii=False, default=str
    )


def _unpack_node(props: dict[str, Any], include_embedding: bool = False) -> dict[str, Any]:
    node_id = props.get("id", "")
    memory = props.get("memory", "")
    metadata: dict[str, Any] = {}
    with suppress(TypeError, json.JSONDecodeError):
        metadata.update(json.loads(props.get("metadata_json") or "{}"))
    for key in (
        "memory_type",
        "status",
        "user_name",
        "created_at",
        "updated_at",
        "mem_cube_id",
        "delete_record_id",
        "delete_time",
    ):
        if props.get(key):
            metadata[key] = props[key]
    if include_embedding and props.get("embedding_json"):
        with suppress(TypeError, json.JSONDecodeError):
            metadata["embedding"] = json.loads(props["embedding_json"])
    return {"id": node_id, "memory": memory, "metadata": metadata}


class HugeGraphGraphDB(BaseGraphDB):
    """HugeGraph-backed graph memory store using pyhugegraph (hugegraph-python)."""

    @require_python_package(
        import_name="pyhugegraph",
        install_command="pip install 'MemoryOS[hugegraph]'",
        install_link="https://github.com/apache/hugegraph-ai",
    )
    def __init__(
        self,
        config: HugeGraphDBConfig,
        vector_index: BaseVectorIndex | None = None,
    ):
        from pyhugegraph.client import PyHugeClient

        self.config = config
        self.user_name = config.user_name
        self._client = PyHugeClient(
            ip=config.ip,
            port=str(config.port),
            graph=config.graph,
            user=config.user or "",
            pwd=config.password or "",
            graphspace=config.graphspace or None,
        )
        self._g = self._client.graph()
        self._gremlin = self._client.gremlin()
        self._traverser = self._client.traverser()

        # The graph provider depends on a backend-neutral vector index. The
        # factory is only a convenience for config-driven construction; callers
        # can inject any BaseVectorIndex implementation directly.
        self._vector_index = vector_index
        if self._vector_index is None and config.vec_config:
            self._vector_index = VectorIndexFactory.from_config(config.vec_config)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def check_health(self) -> None:
        """Raise when graph or configured vector storage cannot serve requests."""
        self._gremlin_exec("g.V().limit(1).count()")
        if self._vector_index is None:
            return
        self._vector_index.check_health()

    def _tenant(self, user_name: str | None = None) -> str:
        return user_name or self.user_name

    @staticmethod
    def _vector_payload(metadata: dict[str, Any], tenant: str) -> dict[str, Any]:
        """Return the fields used to isolate and filter semantic recall."""
        return {
            "user_name": tenant,
            "memory_type": metadata.get("memory_type", ""),
            "status": metadata.get("status", ""),
            "mem_cube_id": metadata.get("mem_cube_id", ""),
        }

    # ------------------------------------------------------------------
    # Vector index coordination
    # ------------------------------------------------------------------

    def _vec_add(self, items: list) -> None:
        """Upsert vectors through the injected backend-neutral index."""
        if self._vector_index is None:
            return
        self._vector_index.upsert(items)

    def _vec_delete(self, ids: list[str]) -> None:
        """Delete by IDs via whichever backend is configured."""
        if self._vector_index is None or not ids:
            return
        self._vector_index.delete(ids)

    def _vec_search(self, vector: list[float], top_k: int, payload_filter: dict) -> list:
        """Search through the injected backend-neutral vector index."""
        if self._vector_index is None:
            return []
        return self._vector_index.search(vector, top_k, payload_filter)

    @staticmethod
    def _gremlin_literal(value: Any) -> str:
        """Encode data as a Groovy/Gremlin literal without executable interpolation."""
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _property_name(value: str) -> str:
        if not _VALID_PROPERTY_NAME.fullmatch(value):
            raise ValueError(f"Invalid HugeGraph property name: {value!r}")
        return value

    def _gremlin_exec(self, query: str) -> list:
        result = self._gremlin.exec(query)
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]

    def _delete_matching_vertices(self, traversal: str) -> int:
        """Keep vector cleanup ahead of the matching graph deletion."""
        ids = [str(node_id) for node_id in self._gremlin_exec(traversal + ".values('id')")]
        self._vec_delete(ids)
        self._gremlin_exec(traversal + ".drop()")
        return len(ids)

    def _sync_vector_status(self, rows: list[dict[str, Any]], tenant: str, status: str) -> None:
        if self._vector_index is None:
            return

        items = []
        for row in rows:
            props = self._parse_valuemap(row)
            try:
                embedding = json.loads(props.get("embedding_json") or "")
            except (TypeError, json.JSONDecodeError):
                continue
            vector_meta = {
                "memory_type": props.get("memory_type", ""),
                "status": status,
                "mem_cube_id": props.get("mem_cube_id", ""),
            }
            items.append(
                VecDBItem(
                    id=str(props.get("id", "")),
                    vector=embedding,
                    payload=self._vector_payload(vector_meta, tenant),
                )
            )
        if items:
            self._vec_add(items)

    def _get_vertex_by_node_id(self, node_id: str, user_name: str | None = None) -> dict | None:
        tenant = self._tenant(user_name)
        node_literal = self._gremlin_literal(node_id)
        tenant_literal = self._gremlin_literal(tenant)
        q = f"g.V({node_literal}).has('user_name', {tenant_literal}).valueMap(true).limit(1)"
        rows = self._gremlin_exec(q)
        if not rows:
            # HugeGraph 1.7 can persist a custom UUID vertex ID through the
            # batch REST API while failing to resolve the same value via
            # g.V(uuid). The vertex REST lookup accepts the same custom ID and
            # does not require adding an index to the shared schema.
            vertices = self._g.getVerticesById([node_id]) or []
            for vertex in vertices:
                props = getattr(vertex, "properties", None)
                if isinstance(props, dict) and props.get("user_name") == tenant:
                    return props
        if not rows:
            return None
        return self._parse_valuemap(rows[0])

    @staticmethod
    def _parse_valuemap(row: dict) -> dict[str, Any]:
        """Flatten gremlin valueMap(true) result into a plain dict."""
        result: dict[str, Any] = {}
        for k, v in row.items():
            if k in ("id", "label"):
                result[k] = v[0] if isinstance(v, list) and len(v) == 1 else v
            elif isinstance(v, list):
                result[k] = v[0] if len(v) == 1 else v
            else:
                result[k] = v
        return result

    # ------------------------------------------------------------------
    # Node Management
    # ------------------------------------------------------------------

    def add_node(
        self, id: str, memory: str, metadata: dict[str, Any], user_name: str | None = None
    ) -> None:
        tenant = self._tenant(user_name)
        meta = metadata.copy()
        embedding = meta.pop("embedding", None)

        props = {
            "id": id,
            "memory": memory,
            "user_name": tenant,
            "memory_type": meta.get("memory_type", ""),
            "status": meta.get("status", ""),
            "mem_cube_id": meta.get("mem_cube_id", ""),
            "delete_record_id": meta.get("delete_record_id", ""),
            "delete_time": meta.get("delete_time", ""),
            "created_at": meta.get("created_at", _now_iso()),
            "updated_at": meta.get("updated_at", _now_iso()),
            "metadata_json": _pack_metadata(meta),
            "embedding_json": json.dumps([float(x) for x in embedding], ensure_ascii=False)
            if embedding
            else "",
        }

        if self._get_vertex_by_node_id(id, user_name) is None:
            self._g.addVertex(_VERTEX_LABEL, props, id=id)
        else:
            # Retrying after a vector failure repairs the vector record and
            # refreshes the already-created graph vertex idempotently.
            self._g.appendVertex(id, props)

        if embedding and self._vector_index:
            self._vec_add(
                [VecDBItem(id=id, vector=embedding, payload=self._vector_payload(meta, tenant))]
            )

    def add_nodes_batch(self, nodes: list[dict[str, Any]], user_name: str | None = None) -> None:
        if not nodes:
            return
        tenant = self._tenant(user_name)
        batch = []
        vec_items = []

        for node in nodes:
            nid = node["id"]
            memory = node["memory"]
            meta = node.get("metadata", {}).copy()
            embedding = meta.pop("embedding", None)
            props = {
                "id": nid,
                "memory": memory,
                "user_name": tenant,
                "memory_type": meta.get("memory_type", ""),
                "status": meta.get("status", ""),
                "mem_cube_id": meta.get("mem_cube_id", ""),
                "delete_record_id": meta.get("delete_record_id", ""),
                "delete_time": meta.get("delete_time", ""),
                "created_at": meta.get("created_at", _now_iso()),
                "updated_at": meta.get("updated_at", _now_iso()),
                "metadata_json": _pack_metadata(meta),
                "embedding_json": json.dumps([float(x) for x in embedding], ensure_ascii=False)
                if embedding
                else "",
            }
            batch.append((nid, props))
            if embedding and self._vector_index:
                vec_items.append(
                    VecDBItem(id=nid, vector=embedding, payload=self._vector_payload(meta, tenant))
                )

        # PyHugeClient.addVertices() does not accept custom vertex IDs. Memory
        # vertices use CUSTOMIZE_STRING IDs, so preserve each MemOS UUID through
        # the public addVertex() API instead of reaching into the private session.
        node_ids = [node_id for node_id, _ in batch]
        existing_query = (
            f"g.V().hasId(within(*{self._gremlin_literal(node_ids)}))"
            f".has('user_name', {self._gremlin_literal(tenant)}).values('id')"
        )
        existing_ids = {str(node_id) for node_id in self._gremlin_exec(existing_query)}
        for node_id, props in batch:
            if node_id in existing_ids:
                self._g.appendVertex(node_id, props)
            else:
                self._g.addVertex(_VERTEX_LABEL, props, id=node_id)
        if vec_items and self._vector_index:
            self._vec_add(vec_items)

    def update_node(self, id: str, fields: dict[str, Any], user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        existing = self._get_vertex_by_node_id(id, user_name)
        if existing is None:
            return
        fields = fields.copy()
        embedding = fields.pop("embedding", None)

        props = {}
        direct_keys = {
            "memory_type",
            "status",
            "mem_cube_id",
            "delete_record_id",
            "delete_time",
            "created_at",
            "updated_at",
            "memory",
        }
        vector_filter_changed = bool({"memory_type", "status", "mem_cube_id"} & fields.keys())
        for k in direct_keys:
            if k in fields:
                props[k] = fields.pop(k)
        props["updated_at"] = _now_iso()

        # Re-fetch existing metadata_json to merge
        try:
            current_meta = json.loads(existing.get("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            current_meta = {}
        current_meta.update(fields)
        props["metadata_json"] = json.dumps(current_meta, ensure_ascii=False, default=str)

        if embedding:
            props["embedding_json"] = json.dumps([float(x) for x in embedding], ensure_ascii=False)

        self._g.appendVertex(id, props)

        vector = embedding
        if vector is None and vector_filter_changed and existing.get("embedding_json"):
            try:
                vector = json.loads(existing["embedding_json"])
            except (TypeError, json.JSONDecodeError):
                vector = None

        if vector and self._vector_index:
            vector_meta = {
                "memory_type": props.get("memory_type", existing.get("memory_type", "")),
                "status": props.get("status", existing.get("status", "")),
                "mem_cube_id": props.get("mem_cube_id", existing.get("mem_cube_id", "")),
            }
            self._vec_add(
                [VecDBItem(id=id, vector=vector, payload=self._vector_payload(vector_meta, tenant))]
            )

    def delete_node(self, id: str, user_name: str | None = None) -> None:
        if self._get_vertex_by_node_id(id, user_name) is None:
            return
        if self._vector_index:
            self._vec_delete([id])
        self._g.removeVertexById(id)

    # ------------------------------------------------------------------
    # Edge Management
    # ------------------------------------------------------------------

    def add_edge(
        self, source_id: str, target_id: str, type: str, user_name: str | None = None
    ) -> None:
        tenant = self._tenant(user_name)
        if (
            self._get_vertex_by_node_id(source_id, user_name) is None
            or self._get_vertex_by_node_id(target_id, user_name) is None
        ):
            logger.warning(
                "Skip cross-tenant or missing edge endpoints: %s -> %s", source_id, target_id
            )
            return
        self._g.addEdge(
            _EDGE_LABEL, source_id, target_id, {_RELATION_TYPE_KEY: type, "user_name": tenant}
        )

    def delete_edge(
        self, source_id: str, target_id: str, type: str, user_name: str | None = None
    ) -> None:
        tenant = self._tenant(user_name)
        source = self._gremlin_literal(source_id)
        target = self._gremlin_literal(target_id)
        relation = self._gremlin_literal(type)
        tenant_literal = self._gremlin_literal(tenant)
        q = (
            f"g.V({source}).outE('{_EDGE_LABEL}')"
            f".has('{_RELATION_TYPE_KEY}', {relation})"
            f".where(inV().hasId({target}))"
            f".has('user_name', {tenant_literal}).drop()"
        )
        self._gremlin_exec(q)

    def edge_exists(
        self,
        source_id: str,
        target_id: str,
        type: str,
        direction: str = "OUTGOING",
        user_name: str | None = None,
    ) -> bool:
        tenant = self._tenant(user_name)
        source = self._gremlin_literal(source_id)
        target = self._gremlin_literal(target_id)
        relation = self._gremlin_literal(type)
        tenant_literal = self._gremlin_literal(tenant)
        if direction == "OUTGOING":
            q = (
                f"g.V({source}).outE('{_EDGE_LABEL}')"
                f".has('{_RELATION_TYPE_KEY}', {relation})"
                f".has('user_name', {tenant_literal})"
                f".where(inV().hasId({target})).limit(1).count()"
            )
        elif direction == "INCOMING":
            q = (
                f"g.V({source}).inE('{_EDGE_LABEL}')"
                f".has('{_RELATION_TYPE_KEY}', {relation})"
                f".has('user_name', {tenant_literal})"
                f".where(outV().hasId({target})).limit(1).count()"
            )
        else:
            q = (
                f"g.V({source}).bothE('{_EDGE_LABEL}')"
                f".has('{_RELATION_TYPE_KEY}', {relation})"
                f".has('user_name', {tenant_literal})"
                f".where(otherV().hasId({target})).limit(1).count()"
            )
        result = self._gremlin_exec(q)
        return bool(result and result[0])

    # ------------------------------------------------------------------
    # Node Queries
    # ------------------------------------------------------------------

    def get_node(self, id: str, include_embedding: bool = False, **kwargs) -> dict[str, Any] | None:
        user_name = kwargs.get("user_name")
        props = self._get_vertex_by_node_id(id, user_name)
        if props is None:
            return None
        return _unpack_node(props, include_embedding)

    def get_nodes(
        self, ids: list[str], include_embedding: bool = False, **kwargs
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        vertices = self._g.getVerticesById(ids)
        if not vertices:
            return []
        result = []
        for v in vertices:
            if (
                v
                and v.properties
                and v.properties.get("user_name") == self._tenant(kwargs.get("user_name"))
            ):
                result.append(_unpack_node(v.properties, include_embedding))
        return result

    def get_edges(
        self, id: str, type: str = "ANY", direction: str = "ANY", user_name: str | None = None
    ) -> list[dict[str, str]]:
        tenant = self._tenant(user_name)
        node_literal = self._gremlin_literal(id)
        tenant_literal = self._gremlin_literal(tenant)
        edge_filter = f"('{_EDGE_LABEL}')"
        type_filter = (
            "" if type == "ANY" else f".has('{_RELATION_TYPE_KEY}', {self._gremlin_literal(type)})"
        )
        user_filter = f".has('user_name', {tenant_literal})"

        if direction == "OUTGOING":
            q = f"g.V({node_literal}).outE{edge_filter}{type_filter}{user_filter}.project('from','to','type').by(outV().id()).by(inV().id()).by('{_RELATION_TYPE_KEY}')"
        elif direction == "INCOMING":
            q = f"g.V({node_literal}).inE{edge_filter}{type_filter}{user_filter}.project('from','to','type').by(outV().id()).by(inV().id()).by('{_RELATION_TYPE_KEY}')"
        else:
            q = (
                f"g.V({node_literal}).bothE{edge_filter}{type_filter}{user_filter}"
                f".project('from','to','type')"
                f".by(outV().id()).by(inV().id()).by('{_RELATION_TYPE_KEY}')"
            )

        rows = self._gremlin_exec(q)
        edges = []
        for row in rows:
            if isinstance(row, dict) and "from" in row:
                edges.append({"from": row["from"], "to": row["to"], "type": row.get("type", "")})
        return edges

    def search_by_kneighbor(
        self,
        source_id: str,
        *,
        max_depth: int = 1,
        limit: int = 10,
        user_name: str | None = None,
        status: str | None = None,
        max_degree: int = 10000,
        skip_degree: int = 0,
    ) -> dict[str, Any]:
        """Run HugeGraph's built-in K-neighbor traverser through PyHugeClient.

        MemOS keeps the stable response shape expected by the recall adapter
        and filters the returned IDs through the public Gremlin manager.
        """
        depth = max(1, int(max_depth))
        result_limit = max(1, int(limit))
        degree = max(1, int(max_degree))
        skipped_degree = max(0, int(skip_degree))
        if skipped_degree and skipped_degree < degree:
            raise ValueError("skip_degree must be 0 or greater than or equal to max_degree")

        response = self._traverser.k_neighbor(str(source_id), depth)
        if not isinstance(response, dict):
            return {
                "source": str(source_id),
                "neighbors": [],
                "paths": [],
                "vertices": [],
                "edges": [],
            }
        payload = response.get("data", response)
        if not isinstance(payload, dict):
            payload = {}
        neighbors = [
            str(item.get("id")) if isinstance(item, dict) and item.get("id") else str(item)
            for item in payload.get("kneighbor", []) or []
            if str(item.get("id") if isinstance(item, dict) else item) != str(source_id)
        ]
        if neighbors:
            tenant = self._tenant(user_name)
            filter_query = (
                f"g.V().hasId(within(*{self._gremlin_literal(neighbors)}))"
                f".hasLabel('{_VERTEX_LABEL}')"
                f".has('user_name', {self._gremlin_literal(tenant)})"
            )
            if status:
                filter_query += f".has('status', {self._gremlin_literal(status)})"
            allowed_ids = {str(node_id) for node_id in self._gremlin_exec(filter_query + ".id()")}
            neighbors = [node_id for node_id in neighbors if node_id in allowed_ids]
        neighbors = neighbors[:result_limit]
        return {
            "source": str(source_id),
            "neighbors": neighbors,
            "paths": [],
            "vertices": [],
            "edges": [],
        }

    def get_neighbors(
        self,
        id: str,
        type: str,
        direction: Literal["in", "out", "both"] = "out",
        user_name: str | None = None,
    ) -> list[str]:
        tenant = self._tenant(user_name)
        step = {"out": "out", "in": "in", "both": "both"}.get(direction, "out")
        q = (
            f"g.V({self._gremlin_literal(id)}).{step}E('{_EDGE_LABEL}')"
            f".has('{_RELATION_TYPE_KEY}', {self._gremlin_literal(type)})"
            f".has('user_name', {self._gremlin_literal(tenant)})"
            f".otherV().has('user_name', {self._gremlin_literal(tenant)}).values('id')"
        )
        return self._gremlin_exec(q)

    def get_path(
        self, source_id: str, target_id: str, max_depth: int = 3, user_name: str | None = None
    ) -> list[str]:
        tenant = self._tenant(user_name)
        depth = max(0, int(max_depth))
        target = self._gremlin_literal(target_id)
        tenant_literal = self._gremlin_literal(tenant)
        q = (
            f"g.V({self._gremlin_literal(source_id)})"
            f".has('user_name', {tenant_literal})"
            f".repeat(bothE('{_EDGE_LABEL}').has('user_name', {tenant_literal})"
            f".otherV().has('user_name', {tenant_literal}).simplePath())"
            f".until(hasId({target}).or().loops().is(gte({depth})))"
            f".hasId({target}).limit(1).path().by('id')"
        )
        rows = self._gremlin_exec(q)
        if rows and isinstance(rows[0], dict):
            return rows[0].get("objects", [])
        return []

    def get_subgraph(
        self, center_id: str, depth: int = 2, user_name: str | None = None
    ) -> dict[str, Any]:
        tenant = self._tenant(user_name)
        depth = max(0, int(depth))
        tenant_literal = self._gremlin_literal(tenant)
        q = (
            f"g.V({self._gremlin_literal(center_id)})"
            f".has('user_name', {tenant_literal})"
            f".repeat(bothE('{_EDGE_LABEL}').has('user_name', {tenant_literal})"
            f".otherV().has('user_name', {tenant_literal}).simplePath())"
            f".emit().times({depth})"
            f".path().by(valueMap(true)).by(valueMap(true))"
        )
        rows = self._gremlin_exec(q)

        core_raw = self._get_vertex_by_node_id(center_id, user_name)
        core_node = _unpack_node(core_raw) if core_raw else None
        neighbors = []
        edges = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple] = set()

        for path in rows:
            objs = path.get("objects", []) if isinstance(path, dict) else []
            for obj in objs:
                if isinstance(obj, dict):
                    nid = obj.get("id", [None])
                    if isinstance(nid, list):
                        nid = nid[0] if nid else None
                    if nid and nid != center_id and nid not in seen_nodes:
                        seen_nodes.add(nid)
                        neighbors.append(_unpack_node(self._parse_valuemap(obj)))
                    # edge
                    if "outV" in obj and "inV" in obj:
                        edge_key = (obj["outV"], obj["inV"], obj.get(_RELATION_TYPE_KEY, ""))
                        if edge_key not in seen_edges:
                            seen_edges.add(edge_key)
                            edges.append(
                                {
                                    "source": obj["outV"],
                                    "target": obj["inV"],
                                    "type": obj.get(_RELATION_TYPE_KEY, ""),
                                }
                            )

        return {"core_node": core_node, "neighbors": neighbors, "edges": edges}

    def get_context_chain(
        self, id: str, type: str = "FOLLOWS", user_name: str | None = None
    ) -> list[str]:
        tenant = self._tenant(user_name)
        tenant_literal = self._gremlin_literal(tenant)
        q = (
            f"g.V({self._gremlin_literal(id)}).has('user_name', {tenant_literal})"
            f".repeat(outE('{_EDGE_LABEL}').has('user_name', {tenant_literal})"
            f".has('{_RELATION_TYPE_KEY}', {self._gremlin_literal(type)})"
            f".inV().has('user_name', {tenant_literal}).simplePath())"
            f".emit().values('id')"
        )
        return self._gremlin_exec(q)

    # ------------------------------------------------------------------
    # Search / Recall
    # ------------------------------------------------------------------

    def search_by_embedding(
        self,
        vector: list[float],
        top_k: int = 5,
        scope: str | None = None,
        status: str | None = None,
        threshold: float | None = None,
        user_name: str | None = None,
        return_fields: list[str] | None = None,
        **kwargs,
    ) -> list[dict]:
        if self._vector_index is None:
            logger.warning("[search_by_embedding] no vec_db configured, returning empty")
            return []
        tenant = self._tenant(user_name)
        payload_filter = {"user_name": tenant}
        if scope:
            payload_filter["memory_type"] = scope
        if status:
            payload_filter["status"] = status

        raw = self._vec_search(vector, top_k=top_k, payload_filter=payload_filter)
        scored_ids = []
        for item in raw:
            score = item.score if hasattr(item, "score") else item.get("score", 0.0)
            if score is None:
                score = 0.0
            if threshold is not None and score < threshold:
                continue
            item_id = item.id if hasattr(item, "id") else item["id"]
            scored_ids.append((item_id, score))

        nodes_by_id = {}
        if return_fields and scored_ids:
            nodes = self.get_nodes(
                [item_id for item_id, _ in scored_ids],
                include_embedding=False,
                user_name=user_name,
            )
            nodes_by_id = {node["id"]: node for node in nodes}

        results = []
        for item_id, score in scored_ids:
            entry: dict[str, Any] = {"id": item_id, "score": score}
            if return_fields:
                node = nodes_by_id.get(item_id)
                if node:
                    for f in return_fields:
                        if f == "memory":
                            entry["memory"] = node.get("memory")
                        elif f in node.get("metadata", {}):
                            entry[f] = node["metadata"][f]
            results.append(entry)
        return results

    def search_by_fulltext(
        self,
        query_words: list[str],
        top_k: int = 10,
        scope: str | None = None,
        status: str | None = None,
        user_name: str | None = None,
        **kwargs,
    ) -> list[dict]:
        tenant = self._tenant(user_name)
        word = query_words[0] if query_words else ""
        filters = [f".has('user_name', {self._gremlin_literal(tenant)})"]
        if scope:
            filters.append(f".has('memory_type', {self._gremlin_literal(scope)})")
        if status:
            filters.append(f".has('status', {self._gremlin_literal(status)})")
        filter_str = "".join(filters)
        limit = max(0, int(top_k))
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}'){filter_str}"
            f".has('memory', Text.contains({self._gremlin_literal(word)}))"
            f".limit({limit}).valueMap(true)"
        )
        rows = self._gremlin_exec(q)
        results = []
        for row in rows:
            props = self._parse_valuemap(row)
            results.append({"id": props.get("id", ""), "score": 1.0})
        return results

    def get_by_metadata(
        self,
        filters: list[dict[str, Any]],
        user_name: str | None = None,
        status: str | None = None,
        **kwargs,
    ) -> list[str]:
        tenant = self._tenant(user_name)
        q = f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', {self._gremlin_literal(tenant)})"
        if status:
            q += f".has('status', {self._gremlin_literal(status)})"
        supported_ops = {"=", "in", "contains", "starts_with", "ends_with", ">", ">=", "<", "<="}
        for f in filters:
            field = f["field"]
            op = f.get("op", "=")
            value = f["value"]
            if op not in supported_ops:
                raise ValueError(f"Unsupported metadata operator: {op}")
            if field in ("memory_type", "status", "user_name") and op == "=":
                q += f".has('{field}', {self._gremlin_literal(value)})"
        q += ".valueMap(true)"
        rows = self._gremlin_exec(q)

        def matches(actual: Any, op: str, expected: Any) -> bool:
            if op == "=":
                return actual == expected
            if op == "in":
                return actual in expected if isinstance(expected, list | tuple | set) else False
            if op == "contains":
                if isinstance(actual, list | tuple | set):
                    candidates = (
                        expected if isinstance(expected, list | tuple | set) else [expected]
                    )
                    return bool(set(actual) & set(candidates))
                return (
                    expected in actual
                    if isinstance(actual, str) and isinstance(expected, str)
                    else False
                )
            if op == "starts_with":
                return (
                    isinstance(actual, str)
                    and isinstance(expected, str)
                    and actual.startswith(expected)
                )
            if op == "ends_with":
                return (
                    isinstance(actual, str)
                    and isinstance(expected, str)
                    and actual.endswith(expected)
                )
            try:
                if op == ">":
                    return actual > expected
                if op == ">=":
                    return actual >= expected
                if op == "<":
                    return actual < expected
                return actual <= expected
            except TypeError:
                return False

        result = []
        for row in rows:
            props = self._parse_valuemap(row)
            node = _unpack_node(props)
            metadata = node["metadata"]
            if all(
                matches(metadata.get(f["field"]), f.get("op", "="), f["value"]) for f in filters
            ):
                result.append(str(node["id"]))
        return result

    # ------------------------------------------------------------------
    # Memory Utilities (Neo4j-compatible extras)
    # ------------------------------------------------------------------

    def get_memory_count(self, memory_type: str, user_name: str | None = None) -> int:
        tenant = self._tenant(user_name)
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('memory_type', {self._gremlin_literal(memory_type)})"
            f".has('user_name', {self._gremlin_literal(tenant)}).count()"
        )
        rows = self._gremlin_exec(q)
        return int(rows[0]) if rows else 0

    def node_not_exist(self, scope: str, user_name: str | None = None) -> bool:
        return self.get_memory_count(scope, user_name) == 0

    def remove_oldest_memory(
        self, memory_type: str, keep_latest: int, user_name: str | None = None
    ) -> None:
        tenant = self._tenant(user_name)
        keep_latest = max(0, int(keep_latest))
        traversal = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('memory_type', {self._gremlin_literal(memory_type)})"
            f".has('user_name', {self._gremlin_literal(tenant)})"
            f".order().by('updated_at', desc)"
            f".range({keep_latest}, -1)"
        )
        self._delete_matching_vertices(traversal)

    def get_all_memory_items(
        self, scope: str, include_embedding: bool = False, status: str | None = None, **kwargs
    ) -> list[dict]:
        tenant = kwargs.get("user_name") or self.user_name
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('memory_type', {self._gremlin_literal(scope)})"
            f".has('user_name', {self._gremlin_literal(tenant)})"
        )
        if status:
            q += f".has('status', {self._gremlin_literal(status)})"
        q += ".valueMap(true)"
        rows = self._gremlin_exec(q)
        return [_unpack_node(self._parse_valuemap(r), include_embedding) for r in rows]

    def get_structure_optimization_candidates(self, scope: str, **kwargs) -> list[dict]:
        tenant = kwargs.get("user_name") or self.user_name
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('memory_type', {self._gremlin_literal(scope)})"
            f".has('status', 'activated')"
            f".has('user_name', {self._gremlin_literal(tenant)})"
            f".filter(bothE('{_EDGE_LABEL}').count().is(0))"
            f".valueMap(true)"
        )
        rows = self._gremlin_exec(q)
        return [_unpack_node(self._parse_valuemap(r)) for r in rows]

    def get_grouped_counts(
        self, group_fields: list[str], user_name: str | None = None, **kwargs
    ) -> list[dict]:
        if not group_fields:
            raise ValueError("group_fields cannot be empty")
        tenant = self._tenant(user_name)
        fields = [self._property_name(field) for field in group_fields]
        traversal = (
            f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', {self._gremlin_literal(tenant)})"
        )
        if len(fields) == 1:
            rows = self._gremlin_exec(
                traversal + f".groupCount().by(values({self._gremlin_literal(fields[0])}))"
            )
            if rows and isinstance(rows[0], dict):
                return [{fields[0]: value, "count": int(count)} for value, count in rows[0].items()]
            return []

        rows = self._gremlin_exec(
            traversal + f".valueMap({', '.join(self._gremlin_literal(field) for field in fields)})"
        )
        grouped: dict[tuple[Any, ...], int] = {}
        for row in rows:
            values = self._parse_valuemap(row)
            key = tuple(values.get(field) for field in fields)
            grouped[key] = grouped.get(key, 0) + 1
        return [
            {**dict(zip(fields, key, strict=True)), "count": count}
            for key, count in grouped.items()
        ]

    def get_neighbors_by_tag(
        self,
        tags: list[str],
        exclude_ids: list[str],
        top_k: int = 5,
        min_overlap: int = 1,
        user_name: str | None = None,
    ) -> list[dict[str, Any]]:
        tenant = self._tenant(user_name)
        exclude_str = self._gremlin_literal(exclude_ids)
        limit = max(0, int(top_k)) * 10
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('user_name', {self._gremlin_literal(tenant)})"
            f".has('status', 'activated')"
            f".not(hasId(*{exclude_str}))"
            f".valueMap(true).limit({limit})"
        )
        rows = self._gremlin_exec(q)
        results = []
        for row in rows:
            props = self._parse_valuemap(row)
            node = _unpack_node(props)
            node_tags = node.get("metadata", {}).get("tags", [])
            if isinstance(node_tags, str):
                node_tags = [node_tags]
            overlap = len(set(tags) & set(node_tags))
            if overlap >= min_overlap:
                node["overlap_count"] = overlap
                results.append(node)
        results.sort(key=lambda x: x.get("overlap_count", 0), reverse=True)
        return results[:top_k]

    def get_children_with_embeddings(
        self, id: str, user_name: str | None = None
    ) -> list[dict[str, Any]]:
        tenant = self._tenant(user_name)
        q = (
            f"g.V({self._gremlin_literal(id)}).outE('{_EDGE_LABEL}')"
            f".has('{_RELATION_TYPE_KEY}', 'PARENT')"
            f".has('user_name', {self._gremlin_literal(tenant)})"
            f".inV().has('user_name', {self._gremlin_literal(tenant)}).valueMap(true)"
        )
        rows = self._gremlin_exec(q)
        result = []
        for row in rows:
            props = self._parse_valuemap(row)
            embedding = None
            if props.get("embedding_json"):
                with suppress(TypeError, json.JSONDecodeError):
                    embedding = json.loads(props["embedding_json"])
            result.append(
                {
                    "id": props.get("id", ""),
                    "memory": props.get("memory", ""),
                    "embedding": embedding,
                }
            )
        return result

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self, user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        prefix = (
            f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', {self._gremlin_literal(tenant)})"
        )
        self._delete_matching_vertices(prefix)

    def export_graph(self, include_embedding: bool = False, **kwargs) -> dict[str, Any]:
        scope = kwargs.get("memory_type")
        tenant = self._tenant(kwargs.get("user_name"))
        tenant_literal = self._gremlin_literal(tenant)
        q = f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', {tenant_literal})"
        if scope:
            if isinstance(scope, list):
                types_str = self._gremlin_literal(scope)
                q += f".has('memory_type', within(*{types_str}))"
            else:
                q += f".has('memory_type', {self._gremlin_literal(scope)})"
        q += ".valueMap(true)"
        node_rows = self._gremlin_exec(q)
        nodes = [_unpack_node(self._parse_valuemap(r), include_embedding) for r in node_rows]

        eq = (
            f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', {tenant_literal})"
            f".outE('{_EDGE_LABEL}').has('user_name', {tenant_literal})"
            f".project('source','target','type')"
            f".by(outV().values('id')).by(inV().values('id')).by('{_RELATION_TYPE_KEY}')"
        )
        edge_rows = self._gremlin_exec(eq)
        return {"nodes": nodes, "edges": edge_rows}

    def import_graph(self, data: dict[str, Any], user_name: str | None = None) -> None:
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        if nodes:
            self.add_nodes_batch(nodes, user_name)
        for edge in edges:
            source = edge.get("source", edge.get("from"))
            target = edge.get("target", edge.get("to"))
            if source is None or target is None:
                raise ValueError("Imported edge requires source/target or from/to")
            self.add_edge(source, target, edge["type"], user_name)

    def deduplicate_nodes(self) -> None:
        raise NotImplementedError

    def detect_conflicts(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    def merge_nodes(self, id1: str, id2: str) -> str:
        raise NotImplementedError

    def delete_node_by_prams(
        self,
        writable_cube_ids: list[str] | None = None,
        memory_ids: list[str] | None = None,
        file_ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        user_name: str | None = None,
    ) -> int:
        if not memory_ids and not file_ids and not filter:
            return 0

        traversal = f"g.V().hasLabel('{_VERTEX_LABEL}')"
        allowed_tenants = writable_cube_ids or [self._tenant(user_name)]
        traversal += f".has('user_name', within(*{self._gremlin_literal(allowed_tenants)}))"
        if memory_ids:
            traversal += f".hasId(within(*{self._gremlin_literal(memory_ids)}))"
        rows = self._gremlin_exec(traversal + ".valueMap(true)")

        def compare(actual: Any, condition: Any) -> bool:
            if not isinstance(condition, dict):
                return actual == condition
            supported = {
                "eq",
                "=",
                "ne",
                "!=",
                "in",
                "nin",
                "not_in",
                "contains",
                "gt",
                "gte",
                "lt",
                "lte",
            }
            for op, expected in condition.items():
                if op not in supported:
                    raise ValueError(f"Unsupported delete filter operator: {op}")
                if op in {"eq", "="} and actual != expected:
                    return False
                if op in {"ne", "!="} and actual == expected:
                    return False
                if op == "in" and actual not in expected:
                    return False
                if op in {"nin", "not_in"} and actual in expected:
                    return False
                if op == "contains":
                    if isinstance(actual, list | tuple | set):
                        if expected not in actual:
                            return False
                    elif not (isinstance(actual, str) and str(expected) in actual):
                        return False
                if op in {"gt", "gte", "lt", "lte"}:
                    try:
                        if op == "gt":
                            passed = actual > expected
                        elif op == "gte":
                            passed = actual >= expected
                        elif op == "lt":
                            passed = actual < expected
                        else:
                            passed = actual <= expected
                    except TypeError:
                        return False
                    if not passed:
                        return False
            return True

        def matches(record: dict[str, Any], expression: dict[str, Any] | None) -> bool:
            if not expression:
                return True
            if "and" in expression:
                return all(matches(record, item) for item in expression["and"])
            if "or" in expression:
                return any(matches(record, item) for item in expression["or"])
            return all(
                compare(record.get(field), condition) for field, condition in expression.items()
            )

        selected_ids = []
        for row in rows:
            node = _unpack_node(self._parse_valuemap(row))
            record = {"id": node["id"], "memory": node["memory"], **node["metadata"]}
            if record.get("user_name") not in allowed_tenants:
                continue
            node_file_ids = record.get("file_ids", []) or []
            file_match = not file_ids or bool(set(file_ids) & set(node_file_ids))
            if file_match and matches(record, filter):
                selected_ids.append(str(node["id"]))

        if not selected_ids:
            return 0
        self._vec_delete(selected_ids)
        self._gremlin_exec(f"g.V().hasId(within(*{self._gremlin_literal(selected_ids)})).drop()")
        return len(selected_ids)

    def get_user_names_by_memory_ids(self, memory_ids: list[str]) -> dict[str, str | None]:
        if not memory_ids:
            return {}
        ids_str = self._gremlin_literal(memory_ids)
        q = f"g.V().hasId(*{ids_str}).project('id', 'user_name').by('id').by('user_name')"
        rows = self._gremlin_exec(q)
        result: dict[str, str | None] = dict.fromkeys(memory_ids)
        for row in rows:
            if isinstance(row, dict):
                result[row.get("id", "")] = row.get("user_name")
        return result

    def exist_user_name(self, user_name: str) -> dict[str, bool]:
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('user_name', {self._gremlin_literal(user_name)}).limit(1).count()"
        )
        rows = self._gremlin_exec(q)
        return {user_name: bool(rows and rows[0])}

    def delete_node_by_mem_cube_id(
        self,
        mem_cube_id: str | None = None,
        delete_record_id: str | None = None,
        hard_delete: bool = False,
    ) -> int:
        if not mem_cube_id or not delete_record_id:
            return 0
        traversal = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('user_name', {self._gremlin_literal(mem_cube_id)})"
        )
        if hard_delete:
            traversal += f".has('delete_record_id', {self._gremlin_literal(delete_record_id)})"
            return self._delete_matching_vertices(traversal)

        rows = self._gremlin_exec(traversal + ".has('status', neq('deleted')).valueMap(true)")
        self._sync_vector_status(rows, mem_cube_id, "deleted")
        ids = [str(self._parse_valuemap(row).get("id", "")) for row in rows]
        if ids:
            now = _now_iso()
            self._gremlin_exec(
                f"g.V().hasId(within(*{self._gremlin_literal(ids)}))"
                f".property('status', 'deleted')"
                f".property('delete_record_id', {self._gremlin_literal(delete_record_id)})"
                f".property('delete_time', {self._gremlin_literal(now)})"
            )
        return len(ids)

    def recover_memory_by_mem_cube_id(
        self,
        mem_cube_id: str | None = None,
        delete_record_id: str | None = None,
    ) -> int:
        if not mem_cube_id or not delete_record_id:
            return 0
        tenant = mem_cube_id
        traversal = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('user_name', {self._gremlin_literal(tenant)})"
            f".has('status', 'deleted')"
        )
        traversal += f".has('delete_record_id', {self._gremlin_literal(delete_record_id)})"
        rows = self._gremlin_exec(traversal + ".valueMap(true)")
        ids = [str(self._parse_valuemap(row).get("id", "")) for row in rows]
        if not ids:
            return 0
        id_traversal = f"g.V().hasId(within(*{self._gremlin_literal(ids)}))"
        self._sync_vector_status(rows, tenant, "activated")
        self._gremlin_exec(
            id_traversal
            + ".property('status', 'activated')"
            + ".property('delete_record_id', '').property('delete_time', '')"
        )
        return len(ids)

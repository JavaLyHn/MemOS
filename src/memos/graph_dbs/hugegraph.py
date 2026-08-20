"""Minimal fixed-schema Apache HugeGraph backend for MemOS graph memories."""

import base64
import gzip
import json

from collections import deque
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from memos.configs.graph_db import HugeGraphDBConfig
from memos.configs.vec_db import VectorDBConfigFactory
from memos.exceptions import MemoryError
from memos.graph_dbs.base import BaseGraphDB
from memos.log import get_logger
from memos.vec_dbs.factory import VecDBFactory
from memos.vec_dbs.item import VecDBItem


logger = get_logger(__name__)


class HugeGraphGraphDB(BaseGraphDB):
    """REST-backed HugeGraph provider using one fixed vertex and edge label."""

    node_label = "Memory"
    edge_label = "MEMORY_RELATION"
    node_property_keys = ("id", "memory", "user_name", "memory_type", "status", "metadata_json")

    def __init__(self, config: HugeGraphDBConfig):
        self.config = config
        self.user_name = config.user_name
        vec_config = (
            VectorDBConfigFactory.model_validate(config.vec_config) if config.vec_config else None
        )
        self.vec_db = VecDBFactory.from_config(vec_config) if vec_config else None
        self.base_url = (
            f"{config.url.rstrip('/')}/graphspaces/{quote(config.graphspace, safe='')}"
            f"/graphs/{quote(config.graph, safe='')}"
        )
        if config.auto_create_schema:
            self.ensure_schema()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        if self.config.user:
            token = base64.b64encode(f"{self.config.user}:{self.config.password}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        try:
            with urlopen(
                Request(url, data=data, headers=headers, method=method),
                timeout=self.config.request_timeout,
            ) as response:
                raw_bytes = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw_bytes = gzip.decompress(raw_bytes)
                raw = raw_bytes.decode()
        except HTTPError as error:
            if allow_not_found and error.code == 404:
                return {}
            body = error.read().decode(errors="replace")[:300]
            raise MemoryError(f"HugeGraph request failed: HTTP {error.code}: {body}") from error
        except URLError as error:
            raise MemoryError(f"HugeGraph request failed: {error.reason}") from error
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise MemoryError("HugeGraph returned a non-JSON response") from error

    @staticmethod
    def _vertex_path(vertex_id: str) -> str:
        return f"/graph/vertices/{quote(json.dumps(vertex_id), safe='')}"

    def _tenant(self, user_name: str | None = None) -> str:
        return user_name or self.user_name

    def _vertices(self, properties: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {"label": self.node_label, "limit": "1000"}
        if properties:
            params["properties"] = json.dumps(properties, separators=(",", ":"))
        return self._request("GET", "/graph/vertices", params=params).get("vertices", [])

    def _find_raw_node(self, node_id: str, user_name: str | None = None) -> dict[str, Any] | None:
        for vertex in self._vertices({"id": node_id}):
            if vertex.get("properties", {}).get("user_name") == self._tenant(user_name):
                return vertex
        return None

    @staticmethod
    def _metadata(properties: dict[str, Any]) -> dict[str, Any]:
        try:
            metadata = json.loads(properties.get("metadata_json", "{}"))
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        metadata.update(
            {key: properties.get(key, "") for key in ("memory_type", "status", "user_name")}
        )
        return metadata

    def _node_dict(self, vertex: dict[str, Any]) -> dict[str, Any]:
        properties = vertex.get("properties", {})
        return {
            "id": properties["id"],
            "memory": properties.get("memory", ""),
            "metadata": self._metadata(properties),
        }

    def _node_properties(
        self, memory: str, metadata: dict[str, Any], user_name: str
    ) -> dict[str, Any]:
        stored = metadata.copy()
        for key in ("user_name", "memory_type", "status"):
            stored.pop(key, None)
        return {
            "memory": memory,
            "user_name": user_name,
            "memory_type": str(metadata.get("memory_type", "")),
            "status": str(metadata.get("status", "activated")),
            "metadata_json": json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
        }

    def ensure_schema(self) -> None:
        """Create only the stable labels, keys, and indexes required by this provider."""
        schema = self._request("GET", "/schema")
        existing = {
            kind: {item["name"] for item in schema.get(kind, [])}
            for kind in ("propertykeys", "vertexlabels", "edgelabels", "indexlabels")
        }
        for name in (*self.node_property_keys, "relation_type"):
            if name not in existing["propertykeys"]:
                self._request(
                    "POST",
                    "/schema/propertykeys",
                    {"name": name, "data_type": "TEXT", "cardinality": "SINGLE"},
                )
        if self.node_label not in existing["vertexlabels"]:
            self._request(
                "POST",
                "/schema/vertexlabels",
                {
                    "name": self.node_label,
                    "id_strategy": "PRIMARY_KEY",
                    "properties": list(self.node_property_keys),
                    "primary_keys": ["id"],
                    "nullable_keys": [name for name in self.node_property_keys if name != "id"],
                },
            )
        if self.edge_label not in existing["edgelabels"]:
            self._request(
                "POST",
                "/schema/edgelabels",
                {
                    "name": self.edge_label,
                    "source_label": self.node_label,
                    "target_label": self.node_label,
                    "frequency": "MULTIPLE",
                    "properties": ["relation_type", "user_name"],
                    "sort_keys": ["relation_type"],
                    "nullable_keys": ["user_name"],
                },
            )
        indexes = (
            ("memos_memory_by_user", "VERTEX_LABEL", self.node_label, "SECONDARY", ["user_name"]),
            (
                "memos_memory_by_scope_status",
                "VERTEX_LABEL",
                self.node_label,
                "SECONDARY",
                ["memory_type", "status"],
            ),
            ("memos_relation_by_user", "EDGE_LABEL", self.edge_label, "SECONDARY", ["user_name"]),
        )
        for name, base_type, base_value, index_type, fields in indexes:
            if name not in existing["indexlabels"]:
                self._request(
                    "POST",
                    "/schema/indexlabels",
                    {
                        "name": name,
                        "base_type": base_type,
                        "base_value": base_value,
                        "index_type": index_type,
                        "fields": fields,
                    },
                )

    def add_node(
        self, id: str, memory: str, metadata: dict[str, Any], user_name: str | None = None
    ) -> None:
        tenant = self._tenant(user_name)
        metadata = metadata.copy()
        embedding = metadata.pop("embedding", None)
        if embedding is not None:
            if self.vec_db is None:
                raise MemoryError(
                    "HugeGraph received an embedding but no vector store is configured"
                )
            metadata["vector_sync"] = "success"
            try:
                self.vec_db.add(
                    [
                        VecDBItem(
                            id=id,
                            vector=embedding,
                            payload={"memory": memory, "user_name": tenant, **metadata},
                        )
                    ]
                )
            except Exception as error:
                raise MemoryError(
                    f"HugeGraph vector write failed for memory {id}: {error}"
                ) from error
        elif self.vec_db is not None:
            metadata["vector_sync"] = "skipped"
        existing = self._find_raw_node(id, tenant)
        properties = self._node_properties(memory, metadata, tenant)
        if existing:
            self._request(
                "PUT",
                f"{self._vertex_path(existing['id'])}?action=append",
                {"label": self.node_label, "properties": properties},
            )
            return
        if self._vertices({"id": id}):
            raise MemoryError(f"Memory node id {id!r} already belongs to another tenant")
        properties["id"] = id
        self._request(
            "POST", "/graph/vertices", {"label": self.node_label, "properties": properties}
        )

    def add_nodes_batch(self, nodes: list[dict[str, Any]], user_name: str | None = None) -> None:
        for node in nodes:
            self.add_node(node["id"], node.get("memory", ""), node.get("metadata", {}), user_name)

    def update_node(self, id: str, fields: dict[str, Any], user_name: str | None = None) -> None:
        node = self.get_node(id, include_embedding=True, user_name=user_name)
        if node is None:
            raise MemoryError(f"Memory node not found: {id}")
        values = fields.copy()
        metadata = node["metadata"]
        metadata.update(values.pop("metadata", {}))
        for key in ("memory_type", "status"):
            if key in values:
                metadata[key] = values.pop(key)
        self.add_node(id, values.pop("memory", node["memory"]), metadata, user_name)

    def delete_node(self, id: str, user_name: str | None = None) -> None:
        if vertex := self._find_raw_node(id, user_name):
            self._request("DELETE", self._vertex_path(vertex["id"]))
            if self.vec_db is not None:
                try:
                    self.vec_db.delete([id])
                except Exception as error:
                    raise MemoryError(
                        f"HugeGraph vector delete failed for memory {id}: {error}"
                    ) from error

    def get_node(
        self, id: str, include_embedding: bool = False, **kwargs: Any
    ) -> dict[str, Any] | None:
        vertex = self._find_raw_node(id, kwargs.get("user_name"))
        if not vertex:
            return None
        node = self._node_dict(vertex)
        if include_embedding and self.vec_db is not None:
            try:
                vector_item = self.vec_db.get_by_id(id)
            except Exception as error:
                raise MemoryError(
                    f"HugeGraph vector read failed for memory {id}: {error}"
                ) from error
            if vector_item is not None:
                node["metadata"]["embedding"] = vector_item.vector
        return node

    def get_nodes(
        self, ids: list, include_embedding: bool = False, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [
            node for node_id in ids if (node := self.get_node(node_id, include_embedding, **kwargs))
        ]

    def _raw_edges(self, vertex: dict[str, Any], direction: str = "OUT") -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/graph/edges",
            params={
                "vertex_id": json.dumps(vertex["id"]),
                "direction": direction,
                "label": self.edge_label,
                "limit": "1000",
            },
        ).get("edges", [])

    def _edge_matches(
        self, source_id: str, target_id: str, relation_type: str, user_name: str | None = None
    ) -> list[dict[str, Any]]:
        source, target = (
            self._find_raw_node(source_id, user_name),
            self._find_raw_node(target_id, user_name),
        )
        if not source or not target:
            return []
        tenant = self._tenant(user_name)
        return [
            edge
            for edge in self._raw_edges(source)
            if edge.get("inV") == target["id"]
            and edge.get("properties", {}).get("relation_type") == relation_type
            and edge.get("properties", {}).get("user_name") == tenant
        ]

    def add_edge(
        self, source_id: str, target_id: str, type: str, user_name: str | None = None
    ) -> None:
        source, target = (
            self._find_raw_node(source_id, user_name),
            self._find_raw_node(target_id, user_name),
        )
        if not source or not target:
            raise MemoryError("Both relationship endpoints must exist in the same tenant")
        if not self._edge_matches(source_id, target_id, type, user_name):
            self._request(
                "POST",
                "/graph/edges",
                {
                    "label": self.edge_label,
                    "outV": source["id"],
                    "inV": target["id"],
                    "properties": {"relation_type": type, "user_name": self._tenant(user_name)},
                },
            )

    def delete_edge(
        self, source_id: str, target_id: str, type: str, user_name: str | None = None
    ) -> None:
        for edge in self._edge_matches(source_id, target_id, type, user_name):
            # HugeGraph edge IDs already carry their type information; unlike a
            # string vertex ID, they must not be JSON-quoted in this path.
            self._request("DELETE", f"/graph/edges/{quote(edge['id'], safe='')}")

    def edge_exists(
        self, source_id: str, target_id: str, type: str, user_name: str | None = None, **_: Any
    ) -> bool:
        return bool(self._edge_matches(source_id, target_id, type, user_name))

    def _node_id_from_vertex_id(self, vertex_id: str) -> str | None:
        data = self._request("GET", self._vertex_path(vertex_id), allow_not_found=True)
        properties = data.get("properties", data.get("vertex", {}).get("properties", {}))
        return properties.get("id")

    def get_neighbors(
        self,
        id: str,
        type: str,
        direction: Literal["in", "out", "both"] = "out",
        user_name: str | None = None,
    ) -> list[str]:
        vertex = self._find_raw_node(id, user_name)
        if not vertex:
            return []
        raw_direction = {"in": "IN", "out": "OUT", "both": "BOTH"}[direction]
        tenant = self._tenant(user_name)
        result = []
        for edge in self._raw_edges(vertex, raw_direction):
            properties = edge.get("properties", {})
            if properties.get("relation_type") != type or properties.get("user_name") != tenant:
                continue
            neighbor_id = edge["inV"] if edge["outV"] == vertex["id"] else edge["outV"]
            if node_id := self._node_id_from_vertex_id(neighbor_id):
                result.append(node_id)
        return result

    def get_path(self, source_id: str, target_id: str, max_depth: int = 3) -> list[str]:
        queue: deque[list[str]] = deque([[source_id]])
        seen = {source_id}
        while queue:
            path = queue.popleft()
            if path[-1] == target_id:
                return path
            if len(path) - 1 == max_depth:
                continue
            for neighbor in self.get_neighbors(path[-1], "RELATED", "both"):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append([*path, neighbor])
        return []

    def get_subgraph(self, center_id: str, depth: int = 2) -> list[str]:
        seen, frontier = {center_id}, {center_id}
        for _ in range(depth):
            frontier = {
                item
                for node in frontier
                for item in self.get_neighbors(node, "RELATED", "both")
                if item not in seen
            }
            seen.update(frontier)
        return list(seen)

    def get_context_chain(self, id: str, type: str = "FOLLOWS") -> list[str]:
        chain = [id]
        while (neighbors := self.get_neighbors(chain[-1], type)) and neighbors[0] not in chain:
            chain.append(neighbors[0])
        return chain

    def search_by_embedding(
        self,
        vector: list[float],
        top_k: int = 5,
        return_fields: list[str] | None = None,
        **kwargs: Any,
    ) -> list[dict]:
        """Retrieve vector candidates and use their IDs to address HugeGraph nodes."""
        if self.vec_db is None:
            return []
        vector_filter: dict[str, Any] = {
            "user_name": kwargs.get("cube_name") or kwargs.get("user_name") or self.user_name,
            "vector_sync": "success",
        }
        if scope := kwargs.get("scope"):
            vector_filter["memory_type"] = scope
        if status := kwargs.get("status"):
            vector_filter["status"] = status
        try:
            results = self.vec_db.search(vector, top_k, filter=vector_filter)
        except Exception as error:
            raise MemoryError(f"HugeGraph vector search failed: {error}") from error
        threshold = kwargs.get("threshold")
        candidates = [
            item
            for item in results
            if threshold is None or item.score is None or item.score >= threshold
        ]
        if not return_fields:
            return [{"id": item.id, "score": item.score} for item in candidates]

        user_name = kwargs.get("cube_name") or kwargs.get("user_name") or self.user_name
        field_aliases = {"source": "sources", "internal_info": "info"}
        hydrated_results: list[dict[str, Any]] = []
        for item in candidates:
            node = self.get_node(item.id, user_name=user_name)
            if node is None:
                logger.warning("Vector hit %s has no matching HugeGraph node", item.id)
                continue
            result: dict[str, Any] = {"id": item.id, "score": item.score}
            metadata = node["metadata"]
            for field in return_fields:
                if field in {"id", "score"}:
                    continue
                if field == "memory":
                    result[field] = node["memory"]
                    continue
                value = metadata.get(field, metadata.get(field_aliases.get(field, "")))
                if value is not None:
                    result[field] = value
            hydrated_results.append(result)
        return hydrated_results

    @staticmethod
    def _matches_filters(metadata: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
        for item in filters:
            field, op, value = item.get("field"), item.get("op", "="), item.get("value")
            actual = metadata.get(field)
            if op in ("=", "eq") and actual != value:
                return False
            if op == "in" and actual not in value:
                return False
            if op == "contains" and value not in (actual or []):
                return False
        return True

    def get_by_metadata(
        self, filters: list[dict[str, Any]], status: str | None = None, user_name: str | None = None
    ) -> list[str]:
        return [
            node["id"]
            for node in self.get_all_memory_items("", status=status, user_name=user_name)
            if self._matches_filters(node["metadata"], filters)
        ]

    def get_all_memory_items(
        self,
        scope: str,
        include_embedding: bool = False,
        status: str | None = None,
        user_name: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[dict]:
        properties: dict[str, Any] = {"user_name": self._tenant(user_name)}
        if scope:
            properties["memory_type"] = scope
        if status:
            properties["status"] = status
        nodes = [self._node_dict(vertex) for vertex in self._vertices(properties)]
        if filter:
            nodes = [
                node
                for node in nodes
                if all(node["metadata"].get(key) == value for key, value in filter.items())
            ]
        return nodes

    def get_structure_optimization_candidates(
        self, scope: str, include_embedding: bool = False
    ) -> list[dict]:
        return self.get_all_memory_items(scope, include_embedding, status="activated")

    def clear(self) -> None:
        for node in self.get_all_memory_items(""):
            self.delete_node(node["id"])

    def export_graph(self, include_embedding: bool = False) -> dict[str, Any]:
        nodes = self.get_all_memory_items("")
        edges = []
        for node in nodes:
            for relation_type in ("RELATED", "PARENT"):
                for target in self.get_neighbors(node["id"], relation_type):
                    edges.append({"source": node["id"], "target": target, "type": relation_type})
        return {"nodes": nodes, "edges": edges}

    def import_graph(self, data: dict[str, Any]) -> None:
        self.add_nodes_batch(data.get("nodes", []))
        for edge in data.get("edges", []):
            self.add_edge(edge["source"], edge["target"], edge["type"])

    def deduplicate_nodes(self) -> None:
        return None

    def detect_conflicts(self) -> list[tuple[str, str]]:
        return []

    def merge_nodes(self, id1: str, id2: str) -> str:
        raise MemoryError("HugeGraph minimal provider does not merge nodes")

    def remove_oldest_memory(
        self, memory_type: str, keep_latest: int, user_name: str | None = None
    ) -> None:
        nodes = self.get_all_memory_items(memory_type, user_name=user_name)
        for node in sorted(nodes, key=lambda item: item["metadata"].get("updated_at", ""))[
            :-keep_latest
        ]:
            self.delete_node(node["id"], user_name)

    def get_edges(self, source_id: str, user_name: str | None = None) -> list[dict[str, str]]:
        source = self._find_raw_node(source_id, user_name)
        if not source:
            return []
        tenant = self._tenant(user_name)
        result = []
        for edge in self._raw_edges(source):
            if edge.get("properties", {}).get("user_name") != tenant:
                continue
            if target := self._node_id_from_vertex_id(edge["inV"]):
                result.append(
                    {
                        "source": source_id,
                        "target": target,
                        "type": edge["properties"]["relation_type"],
                    }
                )
        return result

    def get_grouped_counts(self, user_name: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.get_all_memory_items("", user_name=user_name):
            scope = node["metadata"].get("memory_type", "")
            counts[scope] = counts.get(scope, 0) + 1
        return counts

    def node_not_exist(self, id: str, user_name: str | None = None) -> bool:
        return self.get_node(id, user_name=user_name) is None

    def search_by_fulltext(
        self, query: str, top_k: int = 5, user_name: str | None = None
    ) -> list[dict]:
        return [
            node
            for node in self.get_all_memory_items("", user_name=user_name)
            if query.lower() in node["memory"].lower()
        ][:top_k]

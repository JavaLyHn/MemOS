"""HugeGraph graph provider facade for MemOS."""

import json

from collections.abc import Mapping
from typing import Any

from memos.configs.graph_db import HugeGraphDBConfig
from memos.dependency import require_python_package
from memos.graph_dbs.base import BaseGraphDB
from memos.graph_dbs.hugegraph_codec import (
    GraphProperties,
    now_iso,
    parse_valuemap,
    unpack_node,
    validate_property_name,
)
from memos.graph_dbs.hugegraph_edges import HugeGraphEdgeMixin
from memos.graph_dbs.hugegraph_maintenance import HugeGraphMaintenanceMixin
from memos.graph_dbs.hugegraph_nodes import HugeGraphNodeMixin
from memos.graph_dbs.hugegraph_query import format_gremlin_query
from memos.graph_dbs.hugegraph_schema import (
    EMBEDDING_JSON_PROPERTY,
    MEMORY_TYPE_PROPERTY,
    STATUS_PROPERTY,
    USER_NAME_PROPERTY,
)
from memos.graph_dbs.hugegraph_search import HugeGraphSearchMixin
from memos.log import get_logger
from memos.vec_dbs.index import BaseVectorIndex, VectorIndexFactory
from memos.vec_dbs.item import VecDBItem


logger = get_logger(__name__)


class HugeGraphGraphDB(
    HugeGraphNodeMixin,
    HugeGraphEdgeMixin,
    HugeGraphSearchMixin,
    HugeGraphMaintenanceMixin,
    BaseGraphDB,
):
    """HugeGraph-backed graph memory store using the optional pyhugegraph SDK."""

    @require_python_package(
        import_name="pyhugegraph",
        install_command="pip install 'MemoryOS[hugegraph]'",
        install_link="https://github.com/apache/hugegraph-ai",
    )
    def __init__(
        self,
        config: HugeGraphDBConfig,
        vector_index: BaseVectorIndex | None = None,
    ) -> None:
        from pyhugegraph.client import PyHugeClient

        self.config = config
        self.user_name = config.user_name
        self._logger = logger
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
        self._vector_index = vector_index
        if self._vector_index is None and config.vec_config:
            self._vector_index = VectorIndexFactory.from_config(config.vec_config)

    def check_health(self) -> None:
        """Raise when graph or the configured vector index is unavailable."""
        self._gremlin_exec("g.V().limit(1).count()")
        if self._vector_index is not None:
            self._vector_index.check_health()

    def _tenant(self, user_name: str | None = None) -> str:
        """Resolve the logical tenant for a provider operation."""
        return user_name or self.user_name

    @staticmethod
    def _now_iso() -> str:
        """Expose the shared timestamp helper to operation mixins."""
        return now_iso()

    @staticmethod
    def _vector_payload(metadata: Mapping[str, Any], tenant: str) -> dict[str, Any]:
        """Build the tenant and metadata payload used by vector filtering."""
        return {
            USER_NAME_PROPERTY: tenant,
            MEMORY_TYPE_PROPERTY: metadata.get(MEMORY_TYPE_PROPERTY, ""),
            STATUS_PROPERTY: metadata.get(STATUS_PROPERTY, ""),
            "mem_cube_id": metadata.get("mem_cube_id", ""),
        }

    def _vec_add(self, items: list[VecDBItem]) -> None:
        """Upsert vectors through the backend-neutral contract."""
        if self._vector_index is not None:
            self._vector_index.upsert(items)

    def _vec_delete(self, ids: list[str]) -> None:
        """Delete vectors through the backend-neutral contract."""
        if self._vector_index is not None and ids:
            self._vector_index.delete(ids)

    def _vec_search(
        self,
        vector: list[float],
        top_k: int,
        payload_filter: dict[str, Any],
    ) -> list[VecDBItem]:
        """Search through the backend-neutral vector contract."""
        if self._vector_index is None:
            return []
        return self._vector_index.search(vector, top_k, payload_filter)

    @staticmethod
    def _gremlin_literal(value: Any) -> str:
        """Encode data as a JSON-compatible Gremlin literal."""
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _property_name(value: str) -> str:
        """Validate a dynamic property name before query interpolation."""
        return validate_property_name(value)

    def _gremlin_exec(self, query: str) -> list[Any]:
        """Normalize the pyhugegraph Gremlin response to a list."""
        result = self._gremlin.exec(query)
        if result is None:
            return []
        return result if isinstance(result, list) else [result]

    def _delete_matching_vertices(self, traversal: str) -> int:
        """Remove vectors before deleting the matching graph vertices."""
        ids = [str(node_id) for node_id in self._gremlin_exec(traversal + ".values('id')")]
        self._vec_delete(ids)
        self._gremlin_exec(traversal + ".drop()")
        return len(ids)

    def _sync_vector_status(
        self,
        rows: list[Mapping[str, Any]],
        tenant: str,
        status: str,
    ) -> None:
        """Refresh vector payload status from graph rows."""
        if self._vector_index is None:
            return
        items: list[VecDBItem] = []
        for row in rows:
            properties = parse_valuemap(row)
            try:
                embedding = json.loads(properties.get(EMBEDDING_JSON_PROPERTY) or "")
            except (TypeError, json.JSONDecodeError):
                continue
            metadata = {
                MEMORY_TYPE_PROPERTY: properties.get(MEMORY_TYPE_PROPERTY, ""),
                STATUS_PROPERTY: status,
                "mem_cube_id": properties.get("mem_cube_id", ""),
            }
            items.append(
                VecDBItem(
                    id=str(properties.get("id", "")),
                    vector=embedding,
                    payload=self._vector_payload(metadata, tenant),
                )
            )
        if items:
            self._vec_add(items)

    def _get_vertex_by_node_id(
        self,
        node_id: str,
        user_name: str | None = None,
    ) -> GraphProperties | None:
        """Read one tenant-scoped vertex, with a REST fallback for custom IDs."""
        tenant = self._tenant(user_name)
        query = format_gremlin_query(
            f"""
            g.V({self._gremlin_literal(node_id)})
            .has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})
            .valueMap(true)
            .limit(1)
            """
        )
        rows = self._gremlin_exec(query)
        if rows:
            return parse_valuemap(rows[0])
        vertices = self._g.getVerticesById([node_id]) or []
        for vertex in vertices:
            properties = getattr(vertex, "properties", None)
            if isinstance(properties, dict) and properties.get(USER_NAME_PROPERTY) == tenant:
                return properties
        return None

    @staticmethod
    def _parse_valuemap(row: Mapping[str, Any]) -> GraphProperties:
        """Backward-compatible facade for the shared valueMap decoder."""
        return parse_valuemap(row)

    @staticmethod
    def _unpack_node(
        properties: Mapping[str, Any],
        include_embedding: bool = False,
    ) -> dict[str, Any]:
        """Backward-compatible facade for the shared node decoder."""
        return unpack_node(properties, include_embedding)

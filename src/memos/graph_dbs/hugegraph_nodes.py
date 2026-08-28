"""Node CRUD operations for the HugeGraph graph store."""

import json

from typing import Any

from memos.graph_dbs.hugegraph_codec import (
    GraphProperties,
    MemoryNode,
    build_vertex_properties,
    unpack_node,
)
from memos.graph_dbs.hugegraph_query import format_gremlin_query
from memos.graph_dbs.hugegraph_schema import (
    EMBEDDING_JSON_PROPERTY,
    MEMORY_TYPE_PROPERTY,
    METADATA_JSON_PROPERTY,
    STATUS_PROPERTY,
    USER_NAME_PROPERTY,
    VERTEX_LABEL,
)
from memos.vec_dbs.item import VecDBItem


class HugeGraphNodeMixin:
    """Implement node persistence while delegating transport to the facade."""

    def add_node(
        self,
        id: str,
        memory: str,
        metadata: dict[str, Any],
        user_name: str | None = None,
    ) -> None:
        """Create or refresh one memory node and its optional vector record."""
        tenant = self._tenant(user_name)
        properties, embedding, normalized_metadata = build_vertex_properties(
            id, memory, metadata, tenant
        )
        if self._get_vertex_by_node_id(id, user_name) is None:
            self._g.addVertex(VERTEX_LABEL, properties, id=id)
        else:
            self._g.appendVertex(id, properties)
        if embedding and self._vector_index is not None:
            self._vec_add(
                [
                    VecDBItem(
                        id=id,
                        vector=embedding,
                        payload=self._vector_payload(normalized_metadata, tenant),
                    )
                ]
            )

    def add_nodes_batch(
        self,
        nodes: list[dict[str, Any]],
        user_name: str | None = None,
    ) -> None:
        """Create or refresh multiple memory nodes for one tenant."""
        if not nodes:
            return
        tenant = self._tenant(user_name)
        batch: list[tuple[str, GraphProperties]] = []
        vector_items: list[VecDBItem] = []
        for node in nodes:
            node_id = str(node["id"])
            properties, embedding, normalized_metadata = build_vertex_properties(
                node_id,
                str(node["memory"]),
                node.get("metadata", {}),
                tenant,
            )
            batch.append((node_id, properties))
            if embedding and self._vector_index is not None:
                vector_items.append(
                    VecDBItem(
                        id=node_id,
                        vector=embedding,
                        payload=self._vector_payload(normalized_metadata, tenant),
                    )
                )

        node_ids = [node_id for node_id, _ in batch]
        existing_query = format_gremlin_query(
            f"""
            g.V().hasId(within(*{self._gremlin_literal(node_ids)}))
            .has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})
            .values('id')
            """
        )
        existing_ids = {str(node_id) for node_id in self._gremlin_exec(existing_query)}
        for node_id, properties in batch:
            if node_id in existing_ids:
                self._g.appendVertex(node_id, properties)
            else:
                self._g.addVertex(VERTEX_LABEL, properties, id=node_id)
        if vector_items and self._vector_index is not None:
            self._vec_add(vector_items)

    def update_node(
        self,
        id: str,
        fields: dict[str, Any],
        user_name: str | None = None,
    ) -> None:
        """Update graph properties and refresh vector payload when required."""
        tenant = self._tenant(user_name)
        existing = self._get_vertex_by_node_id(id, user_name)
        if existing is None:
            return
        update_fields = fields.copy()
        embedding = update_fields.pop("embedding", None)
        direct_keys = {
            MEMORY_TYPE_PROPERTY,
            STATUS_PROPERTY,
            "mem_cube_id",
            "delete_record_id",
            "delete_time",
            "created_at",
            "updated_at",
            "memory",
        }
        vector_filter_changed = bool(
            {MEMORY_TYPE_PROPERTY, STATUS_PROPERTY, "mem_cube_id"} & update_fields.keys()
        )
        properties: GraphProperties = {}
        for key in direct_keys:
            if key in update_fields:
                properties[key] = update_fields.pop(key)
        properties["updated_at"] = self._now_iso()
        try:
            current_metadata = json.loads(existing.get(METADATA_JSON_PROPERTY) or "{}")
        except (TypeError, json.JSONDecodeError):
            current_metadata = {}
        current_metadata.update(update_fields)
        properties[METADATA_JSON_PROPERTY] = json.dumps(
            current_metadata, ensure_ascii=False, default=str
        )
        if embedding:
            properties[EMBEDDING_JSON_PROPERTY] = json.dumps(
                [float(value) for value in embedding], ensure_ascii=False
            )
        self._g.appendVertex(id, properties)

        vector = embedding
        if vector is None and vector_filter_changed and existing.get(EMBEDDING_JSON_PROPERTY):
            try:
                vector = json.loads(existing[EMBEDDING_JSON_PROPERTY])
            except (TypeError, json.JSONDecodeError):
                vector = None
        if vector and self._vector_index is not None:
            vector_metadata = {
                MEMORY_TYPE_PROPERTY: properties.get(
                    MEMORY_TYPE_PROPERTY, existing.get(MEMORY_TYPE_PROPERTY, "")
                ),
                STATUS_PROPERTY: properties.get(STATUS_PROPERTY, existing.get(STATUS_PROPERTY, "")),
                "mem_cube_id": properties.get("mem_cube_id", existing.get("mem_cube_id", "")),
            }
            self._vec_add(
                [
                    VecDBItem(
                        id=id,
                        vector=vector,
                        payload=self._vector_payload(vector_metadata, tenant),
                    )
                ]
            )

    def delete_node(self, id: str, user_name: str | None = None) -> None:
        """Delete a node after deleting its optional vector record."""
        if self._get_vertex_by_node_id(id, user_name) is None:
            return
        self._vec_delete([id])
        self._g.removeVertexById(id)

    def get_node(
        self,
        id: str,
        include_embedding: bool = False,
        **kwargs: Any,
    ) -> MemoryNode | None:
        """Return one tenant-scoped memory node."""
        props = self._get_vertex_by_node_id(id, kwargs.get(USER_NAME_PROPERTY))
        return unpack_node(props, include_embedding) if props is not None else None

    def get_nodes(
        self,
        ids: list[str],
        include_embedding: bool = False,
        **kwargs: Any,
    ) -> list[MemoryNode]:
        """Return tenant-scoped memory nodes for the requested IDs."""
        if not ids:
            return []
        vertices = self._g.getVerticesById(ids) or []
        tenant = self._tenant(kwargs.get(USER_NAME_PROPERTY))
        return [
            unpack_node(vertex.properties, include_embedding)
            for vertex in vertices
            if vertex and vertex.properties and vertex.properties.get(USER_NAME_PROPERTY) == tenant
        ]

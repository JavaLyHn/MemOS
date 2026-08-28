"""Search and recall operations for the HugeGraph graph store."""

import heapq
import json

from contextlib import suppress
from typing import Any

from memos.graph_dbs.hugegraph_codec import MemoryNode, matches_filter, parse_valuemap, unpack_node
from memos.graph_dbs.hugegraph_schema import (
    EDGE_LABEL,
    EMBEDDING_JSON_PROPERTY,
    EXPORT_BATCH_SIZE,
    MEMORY_PROPERTY,
    MEMORY_TYPE_PROPERTY,
    RELATION_TYPE_KEY,
    STATUS_PROPERTY,
    USER_NAME_PROPERTY,
    VERTEX_LABEL,
    HugeGraphMemoryStatus,
    HugeGraphMemoryType,
    HugeGraphRelation,
)
from memos.log import get_logger


logger = get_logger(__name__)


class HugeGraphSearchMixin:
    """Implement vector, text, metadata, and graph recall operations."""

    def search_by_embedding(
        self,
        vector: list[float],
        top_k: int = 5,
        scope: str | None = None,
        status: str | None = None,
        threshold: float | None = None,
        user_name: str | None = None,
        return_fields: list[str] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search the configured backend-neutral vector index."""
        if self._vector_index is None:
            logger.warning("[search_by_embedding] no vector index configured")
            return []
        tenant = self._tenant(user_name)
        payload_filter: dict[str, Any] = {USER_NAME_PROPERTY: tenant}
        if scope:
            payload_filter[MEMORY_TYPE_PROPERTY] = scope
        if status:
            payload_filter[STATUS_PROPERTY] = status
        raw_items = self._vec_search(vector, max(0, int(top_k)), payload_filter)
        scored_ids: list[tuple[str, float]] = []
        for item in raw_items:
            score = item.score if hasattr(item, "score") else item.get("score", 0.0)
            score = float(score or 0.0)
            if threshold is not None and score < threshold:
                continue
            item_id = item.id if hasattr(item, "id") else item["id"]
            scored_ids.append((str(item_id), score))

        nodes_by_id: dict[str, MemoryNode] = {}
        if return_fields and scored_ids:
            nodes = self.get_nodes(
                [item_id for item_id, _ in scored_ids],
                include_embedding=False,
                user_name=user_name,
            )
            nodes_by_id = {str(node["id"]): node for node in nodes}

        results: list[dict[str, Any]] = []
        for item_id, score in scored_ids:
            entry: dict[str, Any] = {"id": item_id, "score": score}
            if return_fields:
                node = nodes_by_id.get(item_id)
                if node:
                    for field in return_fields:
                        if field == "memory":
                            entry[field] = node.get("memory")
                        elif field in node.get("metadata", {}):
                            entry[field] = node["metadata"][field]
            results.append(entry)
        return results

    def search_by_fulltext(
        self,
        query_words: list[str],
        top_k: int = 10,
        scope: str | None = None,
        status: str | None = None,
        user_name: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search memory text using HugeGraph's text predicate."""
        tenant = self._tenant(user_name)
        word = query_words[0] if query_words else ""
        filters = [f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"]
        if scope:
            filters.append(f".has('{MEMORY_TYPE_PROPERTY}', {self._gremlin_literal(scope)})")
        if status:
            filters.append(f".has('{STATUS_PROPERTY}', {self._gremlin_literal(status)})")
        query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f"{''.join(filters)}"
            f".has('{MEMORY_PROPERTY}', Text.contains({self._gremlin_literal(word)}))"
            f".limit({max(0, int(top_k))}).valueMap(true)"
        )
        return [
            {"id": parse_valuemap(row).get("id", ""), "score": 1.0}
            for row in self._gremlin_exec(query)
        ]

    def get_by_metadata(
        self,
        filters: list[dict[str, Any]],
        user_name: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Return IDs matching metadata filters within one tenant."""
        tenant = self._tenant(user_name)
        query = f"g.V().hasLabel('{VERTEX_LABEL}').has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
        if status:
            query += f".has('{STATUS_PROPERTY}', {self._gremlin_literal(status)})"
        supported_operators = {
            "=",
            "in",
            "contains",
            "starts_with",
            "ends_with",
            ">",
            ">=",
            "<",
            "<=",
        }
        filter_expression: dict[str, Any] = {"and": []}
        for condition in filters:
            field = str(condition["field"])
            operator = condition.get("op", "=")
            if operator not in supported_operators:
                raise ValueError(f"Unsupported metadata operator: {operator}")
            if (
                field in {MEMORY_TYPE_PROPERTY, STATUS_PROPERTY, USER_NAME_PROPERTY}
                and operator == "="
            ):
                query += f".has('{field}', {self._gremlin_literal(condition['value'])})"
            filter_expression["and"].append(
                {field: condition["value"] if operator == "=" else {operator: condition["value"]}}
            )
        query += ".valueMap(true)"
        result: list[str] = []
        for row in self._gremlin_exec(query):
            node = unpack_node(parse_valuemap(row))
            record = {"id": node["id"], MEMORY_PROPERTY: node["memory"], **node["metadata"]}
            if matches_filter(record, filter_expression):
                result.append(str(node["id"]))
        return result

    def get_memory_count(self, memory_type: str, user_name: str | None = None) -> int:
        """Count tenant-scoped nodes for one memory type."""
        tenant = self._tenant(user_name)
        query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{MEMORY_TYPE_PROPERTY}', {self._gremlin_literal(memory_type)})"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)}).count()"
        )
        rows = self._gremlin_exec(query)
        return int(rows[0]) if rows else 0

    def node_not_exist(self, scope: str, user_name: str | None = None) -> bool:
        """Return whether a tenant has no nodes in the requested scope."""
        return self.get_memory_count(scope, user_name) == 0

    def remove_oldest_memory(
        self,
        memory_type: str,
        keep_latest: int,
        user_name: str | None = None,
    ) -> None:
        """Delete older nodes while preserving the latest records."""
        tenant = self._tenant(user_name)
        traversal = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{MEMORY_TYPE_PROPERTY}', {self._gremlin_literal(memory_type)})"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
            f".order().by('updated_at', desc).range({max(0, int(keep_latest))}, -1)"
        )
        self._delete_matching_vertices(traversal)

    def get_all_memory_items(
        self,
        scope: str,
        include_embedding: bool = False,
        status: str | None = None,
        **kwargs: Any,
    ) -> list[MemoryNode]:
        """Return all memory nodes for a scope and tenant."""
        tenant = self._tenant(kwargs.get("user_name"))
        query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{MEMORY_TYPE_PROPERTY}', {self._gremlin_literal(scope)})"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
        )
        if status:
            query += f".has('{STATUS_PROPERTY}', {self._gremlin_literal(status)})"
        rows = self._gremlin_exec(query + ".valueMap(true)")
        return [unpack_node(parse_valuemap(row), include_embedding) for row in rows]

    def get_structure_optimization_candidates(
        self,
        scope: str,
        **kwargs: Any,
    ) -> list[MemoryNode]:
        """Return activated, isolated nodes eligible for structure optimization."""
        tenant = self._tenant(kwargs.get("user_name"))
        query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{MEMORY_TYPE_PROPERTY}', {self._gremlin_literal(scope)})"
            f".has('{STATUS_PROPERTY}', {self._gremlin_literal(HugeGraphMemoryStatus.ACTIVATED.value)})"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
            f".filter(bothE('{EDGE_LABEL}').count().is(0)).valueMap(true)"
        )
        return [unpack_node(parse_valuemap(row)) for row in self._gremlin_exec(query)]

    def get_grouped_counts(
        self,
        group_fields: list[str],
        user_name: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Count tenant nodes grouped by one or more safe property names."""
        if not group_fields:
            raise ValueError("group_fields cannot be empty")
        tenant = self._tenant(user_name)
        fields = [self._property_name(field) for field in group_fields]
        traversal = f"g.V().hasLabel('{VERTEX_LABEL}').has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
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
            values = parse_valuemap(row)
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
    ) -> list[MemoryNode]:
        """Find the best tag-overlap candidates using bounded graph pages."""
        if top_k <= 0 or not tags:
            return []
        tenant = self._tenant(user_name)
        base_query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
            f".has('{STATUS_PROPERTY}', {self._gremlin_literal(HugeGraphMemoryStatus.ACTIVATED.value)})"
            f".not(hasId(*{self._gremlin_literal(exclude_ids)}))"
        )
        tag_set = set(tags)
        required_overlap = max(1, int(min_overlap))
        ranked: list[tuple[int, int, MemoryNode]] = []
        sequence = 0
        offset = 0
        while True:
            query = f"{base_query}.range({offset}, {offset + EXPORT_BATCH_SIZE}).valueMap(true)"
            rows = self._gremlin_exec(query)
            if not rows:
                break
            for row in rows:
                node = unpack_node(parse_valuemap(row))
                metadata = node.get("metadata", {})
                if metadata.get(MEMORY_TYPE_PROPERTY) == HugeGraphMemoryType.WORKING.value:
                    continue
                if metadata.get("type") == HugeGraphMemoryType.REASONING.value:
                    continue
                node_tags = metadata.get("tags", [])
                if isinstance(node_tags, str):
                    node_tags = [node_tags]
                overlap = len(tag_set & set(node_tags))
                if overlap < required_overlap:
                    continue
                node["overlap_count"] = overlap
                candidate = (overlap, sequence, node)
                sequence += 1
                if len(ranked) < top_k:
                    heapq.heappush(ranked, candidate)
                elif (overlap, candidate[1]) > (ranked[0][0], ranked[0][1]):
                    heapq.heapreplace(ranked, candidate)
            offset += len(rows)
            if len(rows) < EXPORT_BATCH_SIZE:
                break
        ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [item[2] for item in ranked]

    def get_children_with_embeddings(
        self,
        id: str,
        user_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return child nodes and their stored embeddings."""
        tenant = self._tenant(user_name)
        query = (
            f"g.V({self._gremlin_literal(id)}).outE('{EDGE_LABEL}')"
            f".has('{RELATION_TYPE_KEY}', {self._gremlin_literal(HugeGraphRelation.PARENT.value)})"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
            f".inV().has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)}).valueMap(true)"
        )
        result: list[dict[str, Any]] = []
        for row in self._gremlin_exec(query):
            props = parse_valuemap(row)
            embedding = None
            if props.get(EMBEDDING_JSON_PROPERTY):
                with suppress(TypeError, json.JSONDecodeError):
                    embedding = json.loads(props[EMBEDDING_JSON_PROPERTY])
            result.append(
                {
                    "id": str(props.get("id", "")),
                    "memory": str(props.get("memory", "")),
                    "embedding": embedding,
                }
            )
        return result

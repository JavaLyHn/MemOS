"""Import, export, cleanup, and recovery operations for HugeGraph."""

from typing import Any

from memos.graph_dbs.hugegraph_codec import MemoryNode, matches_filter, parse_valuemap, unpack_node
from memos.graph_dbs.hugegraph_schema import (
    EDGE_LABEL,
    EXPORT_BATCH_SIZE,
    MEMORY_TYPE_PROPERTY,
    RELATION_TYPE_KEY,
    STATUS_PROPERTY,
    USER_NAME_PROPERTY,
    VERTEX_LABEL,
    HugeGraphMemoryStatus,
)


class HugeGraphMaintenanceMixin:
    """Implement lifecycle operations without owning the graph transport."""

    def clear(self, user_name: str | None = None) -> None:
        """Delete all nodes and vectors belonging to one tenant."""
        tenant = self._tenant(user_name)
        traversal = f"g.V().hasLabel('{VERTEX_LABEL}').has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
        self._delete_matching_vertices(traversal)

    def _export_base_query(
        self,
        tenant: str,
        memory_type: list[str] | str | None,
        status: list[str] | str | None,
    ) -> str:
        """Build the server-side portion of the export node query."""
        query = f"g.V().hasLabel('{VERTEX_LABEL}').has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
        if memory_type:
            values = memory_type if isinstance(memory_type, list) else [memory_type]
            query += f".has('{MEMORY_TYPE_PROPERTY}', within(*{self._gremlin_literal(values)}))"
        if status:
            values = status if isinstance(status, list) else [status]
            query += f".has('{STATUS_PROPERTY}', within(*{self._gremlin_literal(values)}))"
        else:
            query += f".has('{STATUS_PROPERTY}', neq({self._gremlin_literal(HugeGraphMemoryStatus.DELETED.value)}))"
        return query

    def _export_nodes(
        self,
        base_query: str,
        *,
        page: int | None,
        page_size: int | None,
        filter_expression: dict[str, Any] | None,
        include_embedding: bool,
    ) -> list[MemoryNode]:
        """Export nodes with bounded server pages and post-filtering."""
        if filter_expression:
            selected: list[MemoryNode] = []
            matched_count = 0
            scan_offset = 0
            page_start = ((page or 1) - 1) * (page_size or EXPORT_BATCH_SIZE)
            page_end = page_start + page_size if page_size is not None else None
            while True:
                query = (
                    f"{base_query}.range({scan_offset}, {scan_offset + EXPORT_BATCH_SIZE})"
                    ".valueMap(true)"
                )
                rows = self._gremlin_exec(query)
                if not rows:
                    break
                for row in rows:
                    node = unpack_node(parse_valuemap(row), include_embedding)
                    record = {"id": node["id"], "memory": node["memory"], **node["metadata"]}
                    if not matches_filter(record, filter_expression):
                        continue
                    if page is None or page_end is None or page_start <= matched_count < page_end:
                        selected.append(node)
                    matched_count += 1
                    if page is not None and page_size is not None and len(selected) >= page_size:
                        return selected[:page_size]
                scan_offset += len(rows)
                if len(rows) < EXPORT_BATCH_SIZE:
                    break
            if page is not None and page_size is not None:
                selected = selected[:page_size]
            return selected

        query = f"{base_query}.valueMap(true)"
        if page is not None or page_size is not None:
            normalized_page = max(1, int(page or 1))
            normalized_size = max(1, int(page_size or EXPORT_BATCH_SIZE))
            start = (normalized_page - 1) * normalized_size
            query = f"{base_query}.range({start}, {start + normalized_size}).valueMap(true)"
        rows = self._gremlin_exec(query)
        nodes = [unpack_node(parse_valuemap(row), include_embedding) for row in rows]
        return nodes

    def export_graph(
        self,
        include_embedding: bool = False,
        *,
        page: int | None = None,
        page_size: int | None = None,
        memory_type: list[str] | str | None = None,
        status: list[str] | str | None = None,
        filter: dict[str, Any] | None = None,
        user_name: str | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Export tenant-scoped nodes and edges with real pagination."""
        tenant = self._tenant(user_name)
        base_query = self._export_base_query(tenant, memory_type, status)
        if page is not None or page_size is not None:
            page = max(1, int(page or 1))
            page_size = max(1, int(page_size or EXPORT_BATCH_SIZE))
        nodes = self._export_nodes(
            base_query,
            page=page,
            page_size=page_size,
            filter_expression=filter,
            include_embedding=include_embedding,
        )
        node_ids = [str(node["id"]) for node in nodes]
        if not node_ids:
            edge_rows: list[dict[str, Any]] = []
        else:
            edge_query = (
                f"{base_query}.outE('{EDGE_LABEL}')"
                f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
            )
            if node_ids:
                ids_literal = self._gremlin_literal(node_ids)
                edge_query = (
                    f"g.V().hasId(within(*{ids_literal}))"
                    f".hasLabel('{VERTEX_LABEL}').has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
                    f".outE('{EDGE_LABEL}').has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
                    f".where(inV().hasId(within(*{ids_literal})))"
                )
            edge_query += (
                ".project('source','target','type')"
                f".by(outV().values('id')).by(inV().values('id')).by('{RELATION_TYPE_KEY}')"
            )
            if page is not None and page_size is not None:
                normalized_page = page
                normalized_size = page_size
                start = (normalized_page - 1) * normalized_size
                edge_query += f".range({start}, {start + normalized_size})"
            edge_rows = [row for row in self._gremlin_exec(edge_query) if isinstance(row, dict)]
        return {
            "nodes": nodes,
            "edges": edge_rows,
        }

    def import_graph(self, data: dict[str, Any], user_name: str | None = None) -> None:
        """Import nodes and edges from the serializable export shape."""
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        if nodes:
            self.add_nodes_batch(nodes, user_name)
        for edge in edges:
            source = edge.get("source", edge.get("from"))
            target = edge.get("target", edge.get("to"))
            if source is None or target is None:
                raise ValueError("Imported edge requires source/target or from/to")
            self.add_edge(str(source), str(target), str(edge["type"]), user_name)

    def deduplicate_nodes(self) -> None:
        """HugeGraph does not provide a generic MemOS deduplication policy."""
        raise NotImplementedError

    def detect_conflicts(self) -> list[tuple[str, str]]:
        """HugeGraph does not provide a generic MemOS conflict policy."""
        raise NotImplementedError

    def merge_nodes(self, id1: str, id2: str) -> str:
        """HugeGraph does not provide a generic MemOS merge policy."""
        raise NotImplementedError

    def delete_node_by_prams(
        self,
        writable_cube_ids: list[str] | None = None,
        memory_ids: list[str] | None = None,
        file_ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        user_name: str | None = None,
    ) -> int:
        """Delete nodes matching IDs, file IDs, and filter conditions."""
        if not memory_ids and not file_ids and not filter:
            return 0
        self._validate_delete_filter(filter)
        allowed_tenants = writable_cube_ids or [self._tenant(user_name)]
        query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', within(*{self._gremlin_literal(allowed_tenants)}))"
        )
        if memory_ids:
            query += f".hasId(within(*{self._gremlin_literal(memory_ids)}))"
        rows = self._gremlin_exec(query + ".valueMap(true)")
        selected_ids: list[str] = []
        for row in rows:
            node = unpack_node(parse_valuemap(row))
            record = {"id": node["id"], "memory": node["memory"], **node["metadata"]}
            if record.get(USER_NAME_PROPERTY) not in allowed_tenants:
                continue
            node_file_ids = record.get("file_ids", []) or []
            if file_ids and not set(file_ids) & set(node_file_ids):
                continue
            if matches_filter(record, filter):
                selected_ids.append(str(node["id"]))
        if not selected_ids:
            return 0
        self._vec_delete(selected_ids)
        self._gremlin_exec(f"g.V().hasId(within(*{self._gremlin_literal(selected_ids)})).drop()")
        return len(selected_ids)

    @staticmethod
    def _validate_delete_filter(filter: dict[str, Any] | None) -> None:
        """Keep the legacy delete-filter error contract while sharing evaluation."""
        if not filter:
            return
        operators = {
            "eq",
            "=",
            "ne",
            "!=",
            "in",
            "nin",
            "not_in",
            "contains",
            "gt",
            ">",
            "gte",
            ">=",
            "lt",
            "<",
            "lte",
            "<=",
        }
        for key, value in filter.items():
            if key in {"and", "or"}:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            HugeGraphMaintenanceMixin._validate_delete_filter(item)
                continue
            if isinstance(value, dict):
                for operator in value:
                    if operator not in operators:
                        raise ValueError(f"Unsupported delete filter operator: {operator}")

    def get_user_names_by_memory_ids(self, memory_ids: list[str]) -> dict[str, str | None]:
        """Return the tenant for each requested memory ID."""
        if not memory_ids:
            return {}
        query = (
            f"g.V().hasId(*{self._gremlin_literal(memory_ids)})"
            ".project('id', 'user_name').by('id').by('user_name')"
        )
        result: dict[str, str | None] = dict.fromkeys(memory_ids)
        for row in self._gremlin_exec(query):
            if isinstance(row, dict):
                result[str(row.get("id", ""))] = row.get("user_name")
        return result

    def exist_user_name(self, user_name: str) -> dict[str, bool]:
        """Return whether a tenant has at least one memory node."""
        query = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(user_name)}).limit(1).count()"
        )
        rows = self._gremlin_exec(query)
        return {user_name: bool(rows and rows[0])}

    def delete_node_by_mem_cube_id(
        self,
        mem_cube_id: str | None = None,
        delete_record_id: str | None = None,
        hard_delete: bool = False,
    ) -> int:
        """Soft-delete or hard-delete a memory cube and synchronize vectors."""
        if not mem_cube_id or not delete_record_id:
            return 0
        traversal = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(mem_cube_id)})"
        )
        if hard_delete:
            traversal += f".has('delete_record_id', {self._gremlin_literal(delete_record_id)})"
            return self._delete_matching_vertices(traversal)
        rows = self._gremlin_exec(
            traversal
            + f".has('{STATUS_PROPERTY}', neq('{HugeGraphMemoryStatus.DELETED.value}')).valueMap(true)"
        )
        self._sync_vector_status(rows, mem_cube_id, HugeGraphMemoryStatus.DELETED.value)
        ids = [str(parse_valuemap(row).get("id", "")) for row in rows]
        if ids:
            now = self._now_iso()
            self._gremlin_exec(
                f"g.V().hasId(within(*{self._gremlin_literal(ids)}))"
                f".property('status', '{HugeGraphMemoryStatus.DELETED.value}')"
                f".property('delete_record_id', {self._gremlin_literal(delete_record_id)})"
                f".property('delete_time', {self._gremlin_literal(now)})"
            )
        return len(ids)

    def recover_memory_by_mem_cube_id(
        self,
        mem_cube_id: str | None = None,
        delete_record_id: str | None = None,
    ) -> int:
        """Recover soft-deleted nodes and refresh their vector status."""
        if not mem_cube_id or not delete_record_id:
            return 0
        traversal = (
            f"g.V().hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(mem_cube_id)})"
            f".has('{STATUS_PROPERTY}', '{HugeGraphMemoryStatus.DELETED.value}')"
            f".has('delete_record_id', {self._gremlin_literal(delete_record_id)})"
        )
        rows = self._gremlin_exec(traversal + ".valueMap(true)")
        ids = [str(parse_valuemap(row).get("id", "")) for row in rows]
        if not ids:
            return 0
        self._sync_vector_status(rows, mem_cube_id, HugeGraphMemoryStatus.ACTIVATED.value)
        self._gremlin_exec(
            f"g.V().hasId(within(*{self._gremlin_literal(ids)}))"
            f".property('status', '{HugeGraphMemoryStatus.ACTIVATED.value}')"
            ".property('delete_record_id', '').property('delete_time', '')"
        )
        return len(ids)

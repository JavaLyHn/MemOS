"""Edge and graph-traversal operations for the HugeGraph graph store."""

from typing import Any, Literal, TypeAlias

from memos.graph_dbs.hugegraph_codec import MemoryNode, parse_valuemap, unpack_node
from memos.graph_dbs.hugegraph_schema import (
    EDGE_LABEL,
    RELATION_TYPE_KEY,
    STATUS_PROPERTY,
    USER_NAME_PROPERTY,
    VERTEX_LABEL,
    HugeGraphRelation,
)
from memos.log import get_logger


logger = get_logger(__name__)
EdgeDirection: TypeAlias = Literal["OUTGOING", "INCOMING", "ANY"]


class HugeGraphEdgeMixin:
    """Implement tenant-scoped edge traversal operations."""

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        type: str,
        user_name: str | None = None,
    ) -> None:
        """Create an edge only when both endpoints belong to the tenant."""
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
            EDGE_LABEL,
            source_id,
            target_id,
            {RELATION_TYPE_KEY: type, USER_NAME_PROPERTY: tenant},
        )

    def delete_edge(
        self,
        source_id: str,
        target_id: str,
        type: str,
        user_name: str | None = None,
    ) -> None:
        """Delete one tenant-scoped edge."""
        tenant = self._tenant(user_name)
        source = self._gremlin_literal(source_id)
        target = self._gremlin_literal(target_id)
        relation = self._gremlin_literal(type)
        tenant_literal = self._gremlin_literal(tenant)
        query = (
            f"g.V({source}).outE('{EDGE_LABEL}')"
            f".has('{RELATION_TYPE_KEY}', {relation})"
            f".where(inV().hasId({target}))"
            f".has('{USER_NAME_PROPERTY}', {tenant_literal}).drop()"
        )
        self._gremlin_exec(query)

    def edge_exists(
        self,
        source_id: str,
        target_id: str,
        type: str,
        direction: EdgeDirection = "OUTGOING",
        user_name: str | None = None,
    ) -> bool:
        """Check whether a tenant-scoped edge exists."""
        tenant = self._tenant(user_name)
        source = self._gremlin_literal(source_id)
        target = self._gremlin_literal(target_id)
        relation = self._gremlin_literal(type)
        tenant_literal = self._gremlin_literal(tenant)
        if direction == "OUTGOING":
            step = "outE"
            endpoint = f"where(inV().hasId({target}))"
        elif direction == "INCOMING":
            step = "inE"
            endpoint = f"where(outV().hasId({target}))"
        else:
            step = "bothE"
            endpoint = f"where(otherV().hasId({target}))"
        query = (
            f"g.V({source}).{step}('{EDGE_LABEL}')"
            f".has('{RELATION_TYPE_KEY}', {relation})"
            f".has('{USER_NAME_PROPERTY}', {tenant_literal}).{endpoint}.limit(1).count()"
        )
        result = self._gremlin_exec(query)
        return bool(result and result[0])

    def get_edges(
        self,
        id: str,
        type: str = "ANY",
        direction: EdgeDirection = "ANY",
        user_name: str | None = None,
    ) -> list[dict[str, str]]:
        """Return tenant-scoped edges connected to a node."""
        tenant = self._tenant(user_name)
        node_literal = self._gremlin_literal(id)
        tenant_literal = self._gremlin_literal(tenant)
        type_filter = (
            "" if type == "ANY" else f".has('{RELATION_TYPE_KEY}', {self._gremlin_literal(type)})"
        )
        user_filter = f".has('{USER_NAME_PROPERTY}', {tenant_literal})"
        if direction == "OUTGOING":
            step = "outE"
        elif direction == "INCOMING":
            step = "inE"
        else:
            step = "bothE"
        query = (
            f"g.V({node_literal}).{step}('{EDGE_LABEL}')"
            f"{type_filter}{user_filter}.project('from','to','type')"
            f".by(outV().id()).by(inV().id()).by('{RELATION_TYPE_KEY}')"
        )
        rows = self._gremlin_exec(query)
        return [
            {"from": row["from"], "to": row["to"], "type": row.get("type", "")}
            for row in rows
            if isinstance(row, dict) and "from" in row and "to" in row
        ]

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
        """Return bounded k-neighbors using a server-side Gremlin range.

        The HugeGraph traverser endpoint does not expose a degree/capacity
        argument. Using Gremlin directly keeps the response bounded before it
        reaches Python.
        """
        depth = max(1, int(max_depth))
        result_limit = max(1, int(limit))
        degree = max(1, int(max_degree))
        skipped_degree = max(0, int(skip_degree))
        if skipped_degree and skipped_degree < degree:
            raise ValueError("skip_degree must be 0 or greater than or equal to max_degree")

        tenant = self._tenant(user_name)
        tenant_literal = self._gremlin_literal(tenant)
        query = (
            f"g.V({self._gremlin_literal(source_id)}).hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".repeat(bothE('{EDGE_LABEL}').has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".otherV().hasLabel('{VERTEX_LABEL}')"
            f".has('{USER_NAME_PROPERTY}', {tenant_literal}).simplePath())"
            f".emit().times({depth}).dedup()"
        )
        if status:
            query += f".has('{STATUS_PROPERTY}', {self._gremlin_literal(status)})"
        query += f".range({skipped_degree}, {skipped_degree + degree}).values('id')"
        raw_neighbors = self._gremlin_exec(query)
        neighbors = [str(item) for item in raw_neighbors if str(item) != str(source_id)]
        return {
            "source": str(source_id),
            "neighbors": neighbors[:result_limit],
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
        """Return connected node IDs in the requested direction."""
        tenant = self._tenant(user_name)
        step = {"out": "out", "in": "in", "both": "both"}[direction]
        query = (
            f"g.V({self._gremlin_literal(id)}).{step}E('{EDGE_LABEL}')"
            f".has('{RELATION_TYPE_KEY}', {self._gremlin_literal(type)})"
            f".has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)})"
            f".otherV().has('{USER_NAME_PROPERTY}', {self._gremlin_literal(tenant)}).values('id')"
        )
        return [str(node_id) for node_id in self._gremlin_exec(query)]

    def get_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3,
        user_name: str | None = None,
    ) -> list[str]:
        """Return one tenant-scoped path between two nodes."""
        tenant = self._tenant(user_name)
        depth = max(0, int(max_depth))
        target = self._gremlin_literal(target_id)
        tenant_literal = self._gremlin_literal(tenant)
        query = (
            f"g.V({self._gremlin_literal(source_id)}).has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".repeat(bothE('{EDGE_LABEL}').has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".otherV().has('{USER_NAME_PROPERTY}', {tenant_literal}).simplePath())"
            f".until(hasId({target}).or().loops().is(gte({depth})))"
            f".hasId({target}).limit(1).path().by('id')"
        )
        rows = self._gremlin_exec(query)
        if rows and isinstance(rows[0], dict):
            objects = rows[0].get("objects", [])
            return [str(node_id) for node_id in objects]
        return []

    def get_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        user_name: str | None = None,
    ) -> dict[str, Any]:
        """Return the tenant-scoped subgraph around one node."""
        tenant = self._tenant(user_name)
        traversal_depth = max(0, int(depth))
        tenant_literal = self._gremlin_literal(tenant)
        query = (
            f"g.V({self._gremlin_literal(center_id)}).has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".repeat(bothE('{EDGE_LABEL}').has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".otherV().has('{USER_NAME_PROPERTY}', {tenant_literal}).simplePath())"
            f".emit().times({traversal_depth}).path().by(valueMap(true)).by(valueMap(true))"
        )
        rows = self._gremlin_exec(query)
        core_raw = self._get_vertex_by_node_id(center_id, user_name)
        core_node = unpack_node(core_raw) if core_raw else None
        neighbors: list[MemoryNode] = []
        edges: list[dict[str, str]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()
        for path in rows:
            objects = path.get("objects", []) if isinstance(path, dict) else []
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                node_id = obj.get("id", [None])
                if isinstance(node_id, list):
                    node_id = node_id[0] if node_id else None
                if node_id and node_id != center_id and node_id not in seen_nodes:
                    seen_nodes.add(str(node_id))
                    neighbors.append(unpack_node(parse_valuemap(obj)))
                if "outV" in obj and "inV" in obj:
                    edge_key = (
                        str(obj["outV"]),
                        str(obj["inV"]),
                        str(obj.get(RELATION_TYPE_KEY, "")),
                    )
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append(
                            {
                                "source": edge_key[0],
                                "target": edge_key[1],
                                "type": edge_key[2],
                            }
                        )
        return {"core_node": core_node, "neighbors": neighbors, "edges": edges}

    def get_context_chain(
        self,
        id: str,
        type: str = HugeGraphRelation.FOLLOWS.value,
        user_name: str | None = None,
    ) -> list[str]:
        """Return a tenant-scoped ordered context chain."""
        tenant = self._tenant(user_name)
        tenant_literal = self._gremlin_literal(tenant)
        query = (
            f"g.V({self._gremlin_literal(id)}).has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".repeat(outE('{EDGE_LABEL}').has('{USER_NAME_PROPERTY}', {tenant_literal})"
            f".has('{RELATION_TYPE_KEY}', {self._gremlin_literal(type)})"
            f".inV().has('{USER_NAME_PROPERTY}', {tenant_literal}).simplePath())"
            f".emit().values('id')"
        )
        return [str(node_id) for node_id in self._gremlin_exec(query)]

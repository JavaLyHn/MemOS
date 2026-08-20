"""HugeGraph backend for MemOS using the official hugegraph-python client."""

import json

from datetime import datetime
from typing import Any, Literal

from memos.configs.graph_db import HugeGraphDBConfig
from memos.dependency import require_python_package
from memos.graph_dbs.base import BaseGraphDB
from memos.log import get_logger


logger = get_logger(__name__)

_VERTEX_LABEL = "Memory"
_EDGE_LABEL = "MEMORY_RELATION"
_RELATION_TYPE_KEY = "relation_type"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _pack_metadata(metadata: dict[str, Any]) -> str:
    reserved = {"memory_type", "status", "user_name", "embedding", "created_at", "updated_at"}
    return json.dumps({k: v for k, v in metadata.items() if k not in reserved},
                      ensure_ascii=False, default=str)


def _unpack_node(props: dict[str, Any], include_embedding: bool = False) -> dict[str, Any]:
    node_id = props.get("id", "")
    memory = props.get("memory", "")
    metadata: dict[str, Any] = {}
    try:
        metadata.update(json.loads(props.get("metadata_json") or "{}"))
    except (TypeError, json.JSONDecodeError):
        pass
    for key in ("memory_type", "status", "user_name", "created_at", "updated_at"):
        if props.get(key):
            metadata[key] = props[key]
    if include_embedding and props.get("embedding_json"):
        try:
            metadata["embedding"] = json.loads(props["embedding_json"])
        except (TypeError, json.JSONDecodeError):
            pass
    return {"id": node_id, "memory": memory, "metadata": metadata}


class HugeGraphGraphDB(BaseGraphDB):
    """HugeGraph-backed graph memory store using pyhugegraph (hugegraph-python)."""

    @require_python_package(
        import_name="pyhugegraph",
        install_command="pip install hugegraph-python",
        install_link="https://github.com/apache/hugegraph-ai",
    )
    def __init__(self, config: HugeGraphDBConfig):
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

        # optional vector DB for embedding search
        self._vec_db = None
        self._vec_backend: str | None = None
        self._vec_collection: str | None = None
        if config.vec_config:
            from memos.configs.vec_db import VectorDBConfigFactory
            from memos.vec_dbs.factory import VecDBFactory
            vec_cfg = VectorDBConfigFactory.model_validate(config.vec_config)
            self._vec_db = VecDBFactory.from_config(vec_cfg)
            self._vec_backend = vec_cfg.backend
            # Milvus stores collection_name as list; grab the first entry
            if self._vec_backend == "milvus":
                cn = vec_cfg.config.collection_name
                self._vec_collection = cn[0] if isinstance(cn, list) else cn
            else:
                self._vec_collection = vec_cfg.config.collection_name

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tenant(self, user_name: str | None = None) -> str:
        return user_name or self.user_name

    # ------------------------------------------------------------------
    # Vector DB abstraction helpers (Qdrant vs Milvus)
    # ------------------------------------------------------------------

    def _vec_add(self, items: list) -> None:
        """Add VecDBItems via whichever backend is configured."""
        if self._vec_db is None:
            return
        if self._vec_backend == "milvus":
            from memos.vec_dbs.item import MilvusVecDBItem
            milvus_items = [
                MilvusVecDBItem(id=i.id, vector=i.vector, payload=i.payload) for i in items
            ]
            self._vec_db.add(self._vec_collection, milvus_items)
        else:
            self._vec_db.add(items)

    def _vec_delete(self, ids: list[str]) -> None:
        """Delete by IDs via whichever backend is configured."""
        if self._vec_db is None or not ids:
            return
        if self._vec_backend == "milvus":
            self._vec_db.delete(self._vec_collection, ids)
        else:
            self._vec_db.delete(ids)

    def _vec_search(self, vector: list[float], top_k: int,
                    payload_filter: dict) -> list:
        """Search via whichever backend is configured. Returns list of VecDBItem."""
        if self._vec_db is None:
            return []
        if self._vec_backend == "milvus":
            return self._vec_db.search(
                query_vector=vector,
                query="",
                collection_name=self._vec_collection,
                top_k=top_k,
                filter=payload_filter,
            )
        else:
            return self._vec_db.search(
                query_vector=vector,
                top_k=top_k,
                filter=payload_filter,
            )

    def _gremlin_exec(self, query: str, bindings: dict | None = None) -> list:
        result = self._gremlin.exec(query)
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]

    def _get_vertex_by_node_id(self, node_id: str, user_name: str | None = None) -> dict | None:
        tenant = self._tenant(user_name)
        q = (
            f"g.V().hasLabel('{_VERTEX_LABEL}')"
            f".has('id', '{node_id}')"
            f".has('user_name', '{tenant}')"
            f".valueMap(true).limit(1)"
        )
        rows = self._gremlin_exec(q)
        if not rows:
            return None
        return self._parse_valuemap(rows[0])

    @staticmethod
    def _parse_valuemap(row: dict) -> dict[str, Any]:
        """Flatten gremlin valueMap(true) result into a plain dict."""
        result: dict[str, Any] = {}
        for k, v in row.items():
            if k in ("id", "label"):
                result[k] = v
            elif isinstance(v, list):
                result[k] = v[0] if len(v) == 1 else v
            else:
                result[k] = v
        return result

    # ------------------------------------------------------------------
    # Node Management
    # ------------------------------------------------------------------

    def add_node(self, id: str, memory: str, metadata: dict[str, Any],
                 user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        meta = metadata.copy()
        embedding = meta.pop("embedding", None)

        props = {
            "id": id,
            "memory": memory,
            "user_name": tenant,
            "memory_type": meta.get("memory_type", ""),
            "status": meta.get("status", ""),
            "created_at": meta.get("created_at", _now_iso()),
            "updated_at": meta.get("updated_at", _now_iso()),
            "metadata_json": _pack_metadata(meta),
            "embedding_json": json.dumps(
                [float(x) for x in embedding], ensure_ascii=False
            ) if embedding else "",
        }

        self._g.addVertex(_VERTEX_LABEL, props, id=id)

        if embedding and self._vec_db:
            from memos.vec_dbs.item import VecDBItem
            self._vec_add([VecDBItem(id=id, vector=embedding, payload={"user_name": tenant})])

    def add_nodes_batch(self, nodes: list[dict[str, Any]],
                        user_name: str | None = None) -> None:
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
                "created_at": meta.get("created_at", _now_iso()),
                "updated_at": meta.get("updated_at", _now_iso()),
                "metadata_json": _pack_metadata(meta),
                "embedding_json": json.dumps(
                    [float(x) for x in embedding], ensure_ascii=False
                ) if embedding else "",
            }
            batch.append((_VERTEX_LABEL, props))
            if embedding and self._vec_db:
                from memos.vec_dbs.item import VecDBItem
                vec_items.append(VecDBItem(id=nid, vector=embedding,
                                           payload={"user_name": tenant}))

        self._g.addVertices(batch)
        if vec_items and self._vec_db:
            self._vec_add(vec_items)

    def update_node(self, id: str, fields: dict[str, Any],
                    user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        fields = fields.copy()
        embedding = fields.pop("embedding", None)

        props = {}
        direct_keys = {"memory_type", "status", "created_at", "updated_at", "memory"}
        for k in direct_keys:
            if k in fields:
                props[k] = fields.pop(k)
        props["updated_at"] = _now_iso()

        # Re-fetch existing metadata_json to merge
        existing = self._get_vertex_by_node_id(id, user_name)
        if existing:
            try:
                current_meta = json.loads(existing.get("metadata_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                current_meta = {}
            current_meta.update(fields)
            props["metadata_json"] = json.dumps(current_meta, ensure_ascii=False, default=str)

        if embedding:
            props["embedding_json"] = json.dumps([float(x) for x in embedding],
                                                  ensure_ascii=False)

        self._g.appendVertex(id, props)

    def delete_node(self, id: str, user_name: str | None = None) -> None:
        self._g.removeVertexById(id)
        if self._vec_db:
            try:
                self._vec_delete([id])
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Edge Management
    # ------------------------------------------------------------------

    def add_edge(self, source_id: str, target_id: str, type: str,
                 user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        self._g.addEdge(_EDGE_LABEL, source_id, target_id,
                        {_RELATION_TYPE_KEY: type, "user_name": tenant})

    def delete_edge(self, source_id: str, target_id: str, type: str,
                    user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        q = (
            f"g.V('{source_id}').outE('{_EDGE_LABEL}')"
            f".has('{_RELATION_TYPE_KEY}', '{type}')"
            f".where(inV().hasId('{target_id}'))"
            f".has('user_name', '{tenant}').drop()"
        )
        self._gremlin_exec(q)

    def edge_exists(self, source_id: str, target_id: str, type: str,
                    direction: str = "OUTGOING",
                    user_name: str | None = None) -> bool:
        tenant = self._tenant(user_name)
        if direction == "OUTGOING":
            q = (f"g.V('{source_id}').outE('{_EDGE_LABEL}')"
                 f".has('{_RELATION_TYPE_KEY}', '{type}')"
                 f".has('user_name', '{tenant}')"
                 f".where(inV().hasId('{target_id}')).limit(1).count()")
        elif direction == "INCOMING":
            q = (f"g.V('{source_id}').inE('{_EDGE_LABEL}')"
                 f".has('{_RELATION_TYPE_KEY}', '{type}')"
                 f".has('user_name', '{tenant}')"
                 f".where(outV().hasId('{target_id}')).limit(1).count()")
        else:
            q = (f"g.V('{source_id}').bothE('{_EDGE_LABEL}')"
                 f".has('{_RELATION_TYPE_KEY}', '{type}')"
                 f".has('user_name', '{tenant}')"
                 f".where(otherV().hasId('{target_id}')).limit(1).count()")
        result = self._gremlin_exec(q)
        return bool(result and result[0])

    # ------------------------------------------------------------------
    # Node Queries
    # ------------------------------------------------------------------

    def get_node(self, id: str, include_embedding: bool = False,
                 **kwargs) -> dict[str, Any] | None:
        user_name = kwargs.get("user_name")
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('id', '{id}')"
             f".has('user_name', '{tenant}')"
             f".valueMap(true).limit(1)")
        rows = self._gremlin_exec(q)
        if not rows:
            return None
        props = self._parse_valuemap(rows[0])
        return _unpack_node(props, include_embedding)

    def get_nodes(self, ids: list[str], **kwargs) -> list[dict[str, Any]]:
        if not ids:
            return []
        vertices = self._g.getVerticesById(ids)
        if not vertices:
            return []
        result = []
        for v in vertices:
            if v and v.properties:
                result.append(_unpack_node(v.properties))
        return result

    def get_edges(self, id: str, type: str = "ANY", direction: str = "ANY",
                  user_name: str | None = None) -> list[dict[str, str]]:
        tenant = self._tenant(user_name)
        edge_filter = f".hasLabel('{_EDGE_LABEL}')"
        type_filter = "" if type == "ANY" else f".has('{_RELATION_TYPE_KEY}', '{type}')"
        user_filter = f".has('user_name', '{tenant}')"

        if direction == "OUTGOING":
            q = f"g.V('{id}').outE(){edge_filter}{type_filter}{user_filter}.as('e').inV().as('t').select('e','t').by(valueMap(true))"
        elif direction == "INCOMING":
            q = f"g.V('{id}').inE(){edge_filter}{type_filter}{user_filter}.as('e').outV().as('s').select('e','s').by(valueMap(true))"
        else:
            q = (f"g.V('{id}').bothE(){edge_filter}{type_filter}{user_filter}"
                 f".project('from','to','type')"
                 f".by(outV().id()).by(inV().id()).by('{_RELATION_TYPE_KEY}')")

        rows = self._gremlin_exec(q)
        edges = []
        for row in rows:
            if isinstance(row, dict) and "from" in row:
                edges.append({"from": row["from"], "to": row["to"], "type": row.get("type", "")})
        return edges

    def get_neighbors(self, id: str, type: str,
                      direction: Literal["in", "out", "both"] = "out",
                      user_name: str | None = None) -> list[str]:
        tenant = self._tenant(user_name)
        dir_map = {"out": "out", "in": "in", "both": "both"}
        step = dir_map.get(direction, "out")
        q = (f"g.V('{id}').{step}E('{_EDGE_LABEL}')"
             f".has('{_RELATION_TYPE_KEY}', '{type}')"
             f".has('user_name', '{tenant}')"
             f".otherV().has('id').values('id')")
        return self._gremlin_exec(q)

    def get_path(self, source_id: str, target_id: str, max_depth: int = 3,
                 user_name: str | None = None) -> list[str]:
        q = (f"g.V('{source_id}').repeat(bothE('{_EDGE_LABEL}').otherV().simplePath())"
             f".until(hasId('{target_id}').or().loops().is(gte({max_depth})))"
             f".hasId('{target_id}').limit(1).path().by('id')")
        rows = self._gremlin_exec(q)
        if rows and isinstance(rows[0], dict):
            return rows[0].get("objects", [])
        return []

    def get_subgraph(self, center_id: str, depth: int = 2,
                     user_name: str | None = None) -> dict[str, Any]:
        tenant = self._tenant(user_name)
        q = (f"g.V('{center_id}').repeat(bothE('{_EDGE_LABEL}').otherV().simplePath())"
             f".emit().times({depth}).has('user_name', '{tenant}')"
             f".path().by(valueMap(true)).by(valueMap(true))")
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
                            edges.append({"source": obj["outV"], "target": obj["inV"],
                                          "type": obj.get(_RELATION_TYPE_KEY, "")})

        return {"core_node": core_node, "neighbors": neighbors, "edges": edges}

    def get_context_chain(self, id: str, type: str = "FOLLOWS") -> list[str]:
        q = (f"g.V('{id}').repeat(outE('{_EDGE_LABEL}')"
             f".has('{_RELATION_TYPE_KEY}', '{type}').inV().simplePath())"
             f".emit().values('id')")
        return self._gremlin_exec(q)

    # ------------------------------------------------------------------
    # Search / Recall
    # ------------------------------------------------------------------

    def search_by_embedding(self, vector: list[float], top_k: int = 5,
                             scope: str | None = None, status: str | None = None,
                             threshold: float | None = None,
                             user_name: str | None = None,
                             return_fields: list[str] | None = None,
                             **kwargs) -> list[dict]:
        if self._vec_db is None:
            logger.warning("[search_by_embedding] no vec_db configured, returning empty")
            return []
        tenant = self._tenant(user_name)
        payload_filter = {"user_name": tenant}
        if scope:
            payload_filter["memory_type"] = scope
        if status:
            payload_filter["status"] = status

        raw = self._vec_search(vector, top_k=top_k, payload_filter=payload_filter)
        results = []
        for item in raw:
            score = item.score if hasattr(item, "score") else item.get("score", 0.0)
            if score is None:
                score = 0.0
            if threshold is not None and score < threshold:
                continue
            item_id = item.id if hasattr(item, "id") else item["id"]
            entry: dict[str, Any] = {"id": item_id, "score": score}
            if return_fields:
                node = self.get_node(item_id, include_embedding=False)
                if node:
                    for f in return_fields:
                        if f == "memory":
                            entry["memory"] = node.get("memory")
                        elif f in node.get("metadata", {}):
                            entry[f] = node["metadata"][f]
            results.append(entry)
        return results

    def search_by_fulltext(self, query_words: list[str], top_k: int = 10,
                           scope: str | None = None, status: str | None = None,
                           user_name: str | None = None, **kwargs) -> list[dict]:
        tenant = self._tenant(user_name)
        word = query_words[0] if query_words else ""
        filters = [f".has('user_name', '{tenant}')"]
        if scope:
            filters.append(f".has('memory_type', '{scope}')")
        if status:
            filters.append(f".has('status', '{status}')")
        filter_str = "".join(filters)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}'){filter_str}"
             f".has('memory', textContains('{word}'))"
             f".limit({top_k}).valueMap(true)")
        rows = self._gremlin_exec(q)
        results = []
        for row in rows:
            props = self._parse_valuemap(row)
            results.append({"id": props.get("id", ""), "score": 1.0})
        return results

    def get_by_metadata(self, filters: list[dict[str, Any]],
                        user_name: str | None = None,
                        status: str | None = None, **kwargs) -> list[str]:
        tenant = self._tenant(user_name)
        q = f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', '{tenant}')"
        if status:
            q += f".has('status', '{status}')"
        for f in filters:
            field = f["field"]
            op = f.get("op", "=")
            value = f["value"]
            if field in ("memory_type", "status", "user_name"):
                if op == "=":
                    q += f".has('{field}', '{value}')"
            # Metadata fields are in metadata_json — filter post-fetch for complex ops
        q += ".values('id')"
        ids = self._gremlin_exec(q)
        return [str(i) for i in ids]

    # ------------------------------------------------------------------
    # Memory Utilities (Neo4j-compatible extras)
    # ------------------------------------------------------------------

    def get_memory_count(self, memory_type: str, user_name: str | None = None) -> int:
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('memory_type', '{memory_type}')"
             f".has('user_name', '{tenant}').count()")
        rows = self._gremlin_exec(q)
        return int(rows[0]) if rows else 0

    def node_not_exist(self, scope: str, user_name: str | None = None) -> bool:
        return self.get_memory_count(scope, user_name) == 0

    def remove_oldest_memory(self, memory_type: str, keep_latest: int,
                              user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('memory_type', '{memory_type}')"
             f".has('user_name', '{tenant}')"
             f".order().by('updated_at', desc)"
             f".range({keep_latest}, -1).drop()")
        self._gremlin_exec(q)

    def get_all_memory_items(self, scope: str, include_embedding: bool = False,
                             status: str | None = None, **kwargs) -> list[dict]:
        tenant = kwargs.get("user_name") or self.user_name
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('memory_type', '{scope}')"
             f".has('user_name', '{tenant}')")
        if status:
            q += f".has('status', '{status}')"
        q += ".valueMap(true)"
        rows = self._gremlin_exec(q)
        return [_unpack_node(self._parse_valuemap(r), include_embedding) for r in rows]

    def get_structure_optimization_candidates(self, scope: str, **kwargs) -> list[dict]:
        tenant = kwargs.get("user_name") or self.user_name
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('memory_type', '{scope}')"
             f".has('status', 'activated')"
             f".has('user_name', '{tenant}')"
             f".filter(bothE('{_EDGE_LABEL}').count().is(0))"
             f".valueMap(true)")
        rows = self._gremlin_exec(q)
        return [_unpack_node(self._parse_valuemap(r)) for r in rows]

    def get_grouped_counts(self, group_fields: list[str],
                           user_name: str | None = None, **kwargs) -> list[dict]:
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('user_name', '{tenant}')"
             f".groupCount().by(values({', '.join(repr(f) for f in group_fields)}))")
        rows = self._gremlin_exec(q)
        if rows and isinstance(rows[0], dict):
            return [{"key": k, "count": v} for k, v in rows[0].items()]
        return []

    def get_neighbors_by_tag(self, tags: list[str], exclude_ids: list[str],
                              top_k: int = 5, min_overlap: int = 1,
                              user_name: str | None = None) -> list[dict[str, Any]]:
        tenant = self._tenant(user_name)
        exclude_str = str(exclude_ids)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('user_name', '{tenant}')"
             f".has('status', 'activated')"
             f".not(hasId(*{exclude_str}))"
             f".valueMap(true).limit({top_k * 10})")
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

    def get_children_with_embeddings(self, id: str,
                                      user_name: str | None = None) -> list[dict[str, Any]]:
        tenant = self._tenant(user_name)
        q = (f"g.V('{id}').outE('{_EDGE_LABEL}')"
             f".has('{_RELATION_TYPE_KEY}', 'PARENT')"
             f".has('user_name', '{tenant}')"
             f".inV().valueMap(true)")
        rows = self._gremlin_exec(q)
        result = []
        for row in rows:
            props = self._parse_valuemap(row)
            embedding = None
            if props.get("embedding_json"):
                try:
                    embedding = json.loads(props["embedding_json"])
                except (TypeError, json.JSONDecodeError):
                    pass
            result.append({
                "id": props.get("id", ""),
                "memory": props.get("memory", ""),
                "embedding": embedding,
            })
        return result

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self, user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('user_name', '{tenant}').drop()")
        self._gremlin_exec(q)

    def export_graph(self, include_embedding: bool = False, **kwargs) -> dict[str, Any]:
        scope = kwargs.get("memory_type")
        tenant = self._tenant(kwargs.get("user_name"))
        q = f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', '{tenant}')"
        if scope:
            if isinstance(scope, list):
                types_str = str(scope)
                q += f".has('memory_type', within(*{types_str}))"
            else:
                q += f".has('memory_type', '{scope}')"
        q += ".valueMap(true)"
        node_rows = self._gremlin_exec(q)
        nodes = [_unpack_node(self._parse_valuemap(r), include_embedding) for r in node_rows]

        eq = (f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', '{tenant}')"
              f".outE('{_EDGE_LABEL}').has('user_name', '{tenant}')"
              f".project('from','to','type')"
              f".by(outV().values('id')).by(inV().values('id')).by('{_RELATION_TYPE_KEY}')")
        edge_rows = self._gremlin_exec(eq)
        return {"nodes": nodes, "edges": edge_rows}

    def import_graph(self, data: dict[str, Any], user_name: str | None = None) -> None:
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        if nodes:
            self.add_nodes_batch(nodes, user_name)
        for edge in edges:
            self.add_edge(edge["source_id"], edge["target_id"], edge["type"], user_name)

    def deduplicate_nodes(self) -> None:
        raise NotImplementedError

    def detect_conflicts(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    def merge_nodes(self, id1: str, id2: str) -> str:
        raise NotImplementedError

    def delete_node_by_prams(self, user_name: str | None = None, **kwargs) -> None:
        tenant = self._tenant(user_name)
        q = f"g.V().hasLabel('{_VERTEX_LABEL}').has('user_name', '{tenant}')"
        for k, v in kwargs.items():
            q += f".has('{k}', '{v}')"
        q += ".drop()"
        self._gremlin_exec(q)

    def get_user_names_by_memory_ids(self, memory_ids: list[str]) -> dict[str, str | None]:
        if not memory_ids:
            return {}
        ids_str = str(memory_ids)
        q = (f"g.V().hasId(*{ids_str})"
             f".project('id', 'user_name').by('id').by('user_name')")
        rows = self._gremlin_exec(q)
        result: dict[str, str | None] = {mid: None for mid in memory_ids}
        for row in rows:
            if isinstance(row, dict):
                result[row.get("id", "")] = row.get("user_name")
        return result

    def exist_user_name(self, user_name: str) -> dict[str, bool]:
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('user_name', '{user_name}').limit(1).count()")
        rows = self._gremlin_exec(q)
        return {user_name: bool(rows and rows[0])}

    def delete_node_by_mem_cube_id(self, mem_cube_id: str,
                                    user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('user_name', '{tenant}')"
             f".has('mem_cube_id', '{mem_cube_id}').drop()")
        self._gremlin_exec(q)

    def recover_memory_by_mem_cube_id(self, mem_cube_id: str,
                                       user_name: str | None = None) -> None:
        tenant = self._tenant(user_name)
        q = (f"g.V().hasLabel('{_VERTEX_LABEL}')"
             f".has('user_name', '{tenant}')"
             f".has('mem_cube_id', '{mem_cube_id}')"
             f".property('status', 'activated')")
        self._gremlin_exec(q)

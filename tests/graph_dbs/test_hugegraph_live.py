from __future__ import annotations

import os
import uuid

import pytest

from memos.configs.graph_db import HugeGraphDBConfig
from memos.graph_dbs.hugegraph import HugeGraphGraphDB


pytestmark = pytest.mark.skipif(
    os.getenv("MEMOS_RUN_HUGEGRAPH_LIVE") != "1",
    reason="set MEMOS_RUN_HUGEGRAPH_LIVE=1 to run against HugeGraph and Qdrant",
)


def _backend(tenant: str) -> HugeGraphGraphDB:
    return HugeGraphGraphDB(
        HugeGraphDBConfig(
            ip=os.getenv("HUGEGRAPH_HOST", "127.0.0.1"),
            port=int(os.getenv("HUGEGRAPH_PORT", "18080")),
            graph=os.getenv("HUGEGRAPH_GRAPH", "hugegraph"),
            user_name=tenant,
            vec_config={
                "backend": "qdrant",
                "config": {
                    "host": os.getenv("QDRANT_HOST", "127.0.0.1"),
                    "port": int(os.getenv("QDRANT_PORT", "6333")),
                    "collection_name": "memos_hugegraph_live",
                    "vector_dimension": 3,
                    "distance_metric": "cosine",
                },
            },
        )
    )


def test_live_crud_recall_edges_cleanup_and_tenant_isolation() -> None:
    tenant_a = f"live-a-{uuid.uuid4()}"
    tenant_b = f"live-b-{uuid.uuid4()}"
    node_a = str(uuid.uuid4())
    node_b = str(uuid.uuid4())
    backend_a = _backend(tenant_a)
    backend_b = _backend(tenant_b)

    try:
        backend_a.add_node(
            node_a,
            "Alice prefers concise answers.",
            {
                "embedding": [1.0, 0.0, 0.0],
                "memory_type": "LongTermMemory",
                "status": "activated",
                "mem_cube_id": tenant_a,
            },
        )
        backend_a.add_node(
            node_b,
            "Use a short response.",
            {
                "embedding": [0.9, 0.1, 0.0],
                "memory_type": "WorkingMemory",
                "status": "activated",
                "mem_cube_id": tenant_a,
            },
        )
        backend_a.add_edge(node_a, node_b, "SUPPORTS")

        assert backend_a.get_node(node_a, include_embedding=True)["memory"] == (
            "Alice prefers concise answers."
        )
        grouped_counts = backend_a.get_grouped_counts(["memory_type"])
        assert {row["memory_type"]: row["count"] for row in grouped_counts} == {
            "LongTermMemory": 1,
            "WorkingMemory": 1,
        }
        assert backend_a.get_neighbors(node_a, "SUPPORTS") == [node_b]
        hits = backend_a.search_by_embedding(
            [1.0, 0.0, 0.0],
            top_k=5,
            scope="LongTermMemory",
            status="activated",
            return_fields=["memory", "memory_type", "status"],
        )
        assert hits[0]["id"] == node_a
        assert hits[0]["memory"] == "Alice prefers concise answers."
        fulltext_hits = backend_a.search_by_fulltext(
            ["concise"],
            top_k=5,
            scope="LongTermMemory",
            status="activated",
        )
        assert fulltext_hits == [{"id": node_a, "score": 1.0}]

        assert backend_b.get_node(node_a) is None
        assert backend_b.search_by_embedding([1.0, 0.0, 0.0], top_k=5) == []
        backend_b.delete_node(node_a)
        assert backend_a.get_node(node_a) is not None
    finally:
        backend_a.delete_node(node_b)
        backend_a.delete_node(node_a)

    assert backend_a.get_node(node_a) is None
    assert backend_a.search_by_embedding([1.0, 0.0, 0.0], top_k=5) == []

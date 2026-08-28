from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from memos.graph_dbs.hugegraph import HugeGraphGraphDB
from memos.graph_dbs.hugegraph_query import format_gremlin_query
from memos.vec_dbs.index import BaseVectorIndex


MEMORY_ID = "11111111-1111-4111-8111-111111111111"


def test_format_gremlin_query_dedents_multiline_templates():
    assert (
        format_gremlin_query(
            """
        g.V()
          .hasLabel('memory')
        """
        )
        == "g.V().hasLabel('memory')"
    )


def _backend_with_vector_index() -> HugeGraphGraphDB:
    backend = HugeGraphGraphDB.__new__(HugeGraphGraphDB)
    backend.user_name = "tenant-1"
    backend._g = MagicMock()
    backend._traverser = MagicMock()
    backend._vector_index = MagicMock(spec=BaseVectorIndex)
    backend._gremlin = MagicMock()
    backend._gremlin.exec.return_value = []
    backend.config = SimpleNamespace(graph="hugegraph")
    return backend


def test_gremlin_uses_public_pyhugegraph_manager():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [[3], [4]]

    assert backend._gremlin_exec("g.V().count()") == [3]
    assert backend._gremlin_exec("g.E().count()") == [4]

    assert backend._gremlin.exec.call_args_list[0].args == ("g.V().count()",)
    assert backend._gremlin.exec.call_args_list[1].args == ("g.E().count()",)


def test_health_checks_graph_and_vector_collection():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(return_value=[0])

    backend.check_health()

    backend._gremlin_exec.assert_called_once_with("g.V().limit(1).count()")
    backend._vector_index.check_health.assert_called_once_with()


def test_health_rejects_missing_vector_collection():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(return_value=[0])
    backend._vector_index.check_health.side_effect = ConnectionError(
        "Vector collection unavailable"
    )

    with pytest.raises(ConnectionError, match="Vector collection"):
        backend.check_health()


def test_fulltext_search_uses_hugegraph_text_predicate():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(return_value=[])

    backend.search_by_fulltext(["needle"], user_name="tenant-1")

    query = backend._gremlin_exec.call_args.args[0]
    assert ".has('memory', Text.contains(\"needle\"))" in query
    assert "textContains" not in query


def test_add_node_writes_every_vector_filter_field():
    backend = _backend_with_vector_index()

    backend.add_node(
        MEMORY_ID,
        "remember this",
        {
            "embedding": [0.1, 0.2],
            "memory_type": "LongTermMemory",
            "status": "activated",
            "mem_cube_id": "cube-1",
        },
    )

    vector_item = backend._vector_index.upsert.call_args.args[0][0]
    assert str(vector_item.id) == MEMORY_ID
    assert vector_item.payload == {
        "user_name": "tenant-1",
        "memory_type": "LongTermMemory",
        "status": "activated",
        "mem_cube_id": "cube-1",
    }


def test_add_nodes_batch_writes_every_vector_filter_field():
    backend = _backend_with_vector_index()

    backend.add_nodes_batch(
        [
            {
                "id": MEMORY_ID,
                "memory": "remember this",
                "metadata": {
                    "embedding": [0.1, 0.2],
                    "memory_type": "WorkingMemory",
                    "status": "activated",
                    "mem_cube_id": "cube-1",
                },
            }
        ]
    )

    vector_item = backend._vector_index.upsert.call_args.args[0][0]
    assert vector_item.payload == {
        "user_name": "tenant-1",
        "memory_type": "WorkingMemory",
        "status": "activated",
        "mem_cube_id": "cube-1",
    }
    backend._g.addVertex.assert_called_once()
    label, properties = backend._g.addVertex.call_args.args
    assert label == "Memory"
    assert properties["id"] == MEMORY_ID
    assert backend._g.addVertex.call_args.kwargs == {"id": MEMORY_ID}


def test_add_edge_uses_fixed_schema_label_and_relation_property():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(return_value={"id": MEMORY_ID})

    backend.add_edge(MEMORY_ID, "22222222-2222-4222-8222-222222222222", "PARENT")

    backend._g.addEdge.assert_called_once_with(
        "MEMORY_RELATION",
        MEMORY_ID,
        "22222222-2222-4222-8222-222222222222",
        {"relation_type": "PARENT", "user_name": "tenant-1"},
    )


def test_add_edge_rejects_endpoint_outside_tenant():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(side_effect=[{"id": MEMORY_ID}, None])

    backend.add_edge(MEMORY_ID, "22222222-2222-4222-8222-222222222222", "PARENT")

    backend._g.addEdge.assert_not_called()


def test_k_neighbor_applies_server_side_result_bound():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.return_value = ["neighbor-1"]

    result = backend.search_by_kneighbor(
        MEMORY_ID,
        max_depth=2,
        limit=7,
        user_name="tenant-1",
        status="activated",
        max_degree=2,
    )

    assert result["neighbors"] == ["neighbor-1"]
    assert result["paths"] == []
    assert result["edges"] == []
    backend._traverser.k_neighbor.assert_not_called()
    query = backend._gremlin.exec.call_args.args[0]
    assert ".range(0, 2)" in query
    assert ".has('user_name', \"tenant-1\")" in query
    assert ".has('status', \"activated\")" in query


def test_neighbors_by_tag_scans_pages_and_excludes_non_long_term_nodes():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(
        return_value=[
            {
                "id": ["working"],
                "memory": ["working memory"],
                "user_name": ["tenant-1"],
                "memory_type": ["WorkingMemory"],
                "status": ["activated"],
                "metadata_json": ['{"tags":["topic"]}'],
            },
            {
                "id": ["reasoning"],
                "memory": ["reasoning memory"],
                "user_name": ["tenant-1"],
                "memory_type": ["LongTermMemory"],
                "status": ["activated"],
                "metadata_json": ['{"tags":["topic"],"type":"reasoning"}'],
            },
            {
                "id": ["candidate"],
                "memory": ["candidate memory"],
                "user_name": ["tenant-1"],
                "memory_type": ["LongTermMemory"],
                "status": ["activated"],
                "metadata_json": ['{"tags":["topic","python"]}'],
            },
        ]
    )

    result = backend.get_neighbors_by_tag(
        tags=["topic", "python"], exclude_ids=[], top_k=1, min_overlap=1
    )

    assert [node["id"] for node in result] == ["candidate"]
    query = backend._gremlin_exec.call_args.args[0]
    assert ".range(0, 1000)" in query
    assert ".limit(" not in query


def test_delete_node_does_not_mutate_unknown_tenant_node():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(return_value=None)

    backend.delete_node(MEMORY_ID)

    backend._g.removeVertexById.assert_not_called()
    backend._vector_index.delete.assert_not_called()


def test_get_nodes_filters_vertices_by_tenant():
    backend = _backend_with_vector_index()
    backend._g.getVerticesById.return_value = [
        SimpleNamespace(properties={"id": MEMORY_ID, "memory": "mine", "user_name": "tenant-1"}),
        SimpleNamespace(
            properties={
                "id": "22222222-2222-4222-8222-222222222222",
                "memory": "not mine",
                "user_name": "tenant-2",
            }
        ),
    ]

    nodes = backend.get_nodes([MEMORY_ID, "22222222-2222-4222-8222-222222222222"])

    assert [node["id"] for node in nodes] == [MEMORY_ID]


def test_single_node_lookup_falls_back_to_vertex_rest_lookup_for_hugegraph_uuid():
    backend = _backend_with_vector_index()
    properties = {
        "id": MEMORY_ID,
        "memory": "stored memory",
        "user_name": "tenant-1",
        "metadata_json": "{}",
    }
    backend._gremlin_exec = MagicMock(return_value=[])
    backend._g.getVerticesById.return_value = [SimpleNamespace(properties=properties)]

    assert backend._get_vertex_by_node_id(MEMORY_ID)["id"] == MEMORY_ID
    assert backend.get_node(MEMORY_ID)["id"] == MEMORY_ID

    queries = [call.args[0] for call in backend._gremlin_exec.call_args_list]
    assert queries[0].startswith(f'g.V("{MEMORY_ID}")')
    assert queries[1].startswith(f'g.V("{MEMORY_ID}")')
    assert backend._g.getVerticesById.call_args_list == [
        (([MEMORY_ID],),),
        (([MEMORY_ID],),),
    ]


def test_grouped_counts_names_single_group_field_like_neo4j():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(return_value=[{"LongTermMemory": 3, "WorkingMemory": 1}])

    assert backend.get_grouped_counts(["memory_type"]) == [
        {"memory_type": "LongTermMemory", "count": 3},
        {"memory_type": "WorkingMemory", "count": 1},
    ]


def test_grouped_counts_supports_multiple_fields():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(
        return_value=[
            {"memory_type": ["LongTermMemory"], "status": ["activated"]},
            {"memory_type": ["LongTermMemory"], "status": ["activated"]},
            {"memory_type": ["WorkingMemory"], "status": ["archived"]},
        ]
    )

    assert backend.get_grouped_counts(["memory_type", "status"]) == [
        {"memory_type": "LongTermMemory", "status": "activated", "count": 2},
        {"memory_type": "WorkingMemory", "status": "archived", "count": 1},
    ]


def test_update_embedding_upserts_vector_with_updated_filters():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(
        return_value={
            "id": MEMORY_ID,
            "memory_type": "LongTermMemory",
            "status": "activated",
            "mem_cube_id": "cube-1",
            "metadata_json": "{}",
        }
    )

    backend.update_node(MEMORY_ID, {"embedding": [0.3, 0.4], "status": "archived"})

    vector_item = backend._vector_index.upsert.call_args.args[0][0]
    assert vector_item.payload == {
        "user_name": "tenant-1",
        "memory_type": "LongTermMemory",
        "status": "archived",
        "mem_cube_id": "cube-1",
    }


def test_exported_edges_can_be_imported_without_translation():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(
        side_effect=[
            [
                {
                    "id": [MEMORY_ID],
                    "memory": ["source"],
                    "user_name": ["tenant-1"],
                    "status": ["activated"],
                },
                {
                    "id": ["22222222-2222-4222-8222-222222222222"],
                    "memory": ["target"],
                    "user_name": ["tenant-1"],
                    "status": ["activated"],
                },
            ],
            [
                {
                    "source": MEMORY_ID,
                    "target": "22222222-2222-4222-8222-222222222222",
                    "type": "PARENT",
                }
            ],
        ]
    )
    exported = backend.export_graph()
    backend.add_nodes_batch = MagicMock()
    backend.add_edge = MagicMock()

    backend.import_graph(exported)

    backend.add_edge.assert_called_once_with(
        MEMORY_ID,
        "22222222-2222-4222-8222-222222222222",
        "PARENT",
        None,
    )


def test_export_graph_pushes_pagination_and_filters_to_hugegraph():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(return_value=[])

    backend.export_graph(
        page=2,
        page_size=1,
        memory_type=["LongTermMemory"],
        status=["activated"],
        user_name="tenant-1",
    )

    queries = [call.args[0] for call in backend._gremlin_exec.call_args_list]
    node_query = next(query for query in queries if ".valueMap(true)" in query)
    assert ".range(1, 2)" in node_query
    assert 'within(*["LongTermMemory"])' in node_query
    assert ".has('status', within(*[\"activated\"]))" in node_query


def test_export_graph_applies_metadata_filter_before_page_slice():
    backend = _backend_with_vector_index()
    backend._gremlin_exec = MagicMock(
        side_effect=[
            [
                {
                    "id": [MEMORY_ID],
                    "memory": ["keep"],
                    "user_name": ["tenant-1"],
                    "status": ["activated"],
                    "metadata_json": ['{"category":"keep"}'],
                },
                {
                    "id": ["22222222-2222-4222-8222-222222222222"],
                    "memory": ["drop"],
                    "user_name": ["tenant-1"],
                    "status": ["activated"],
                    "metadata_json": ['{"category":"drop"}'],
                },
            ],
            [],
            [],
        ]
    )

    exported = backend.export_graph(
        page=1,
        page_size=1,
        filter={"category": "keep"},
        user_name="tenant-1",
    )

    assert [node["id"] for node in exported["nodes"]] == [MEMORY_ID]
    assert ".range(0, 1000)" in backend._gremlin_exec.call_args_list[0].args[0]


def test_import_graph_accepts_legacy_from_to_edge_shape():
    backend = _backend_with_vector_index()
    backend.add_edge = MagicMock()

    backend.import_graph(
        {
            "edges": [
                {
                    "from": MEMORY_ID,
                    "to": "22222222-2222-4222-8222-222222222222",
                    "type": "PARENT",
                }
            ]
        }
    )

    backend.add_edge.assert_called_once_with(
        MEMORY_ID,
        "22222222-2222-4222-8222-222222222222",
        "PARENT",
        None,
    )


def test_get_node_encodes_untrusted_id_as_one_gremlin_literal():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.return_value = []
    hostile_id = "memory').drop(); g.V('"

    backend.get_node(hostile_id)

    query = backend._gremlin.exec.call_args.args[0]
    assert query.startswith(f"g.V({backend._gremlin_literal(hostile_id)})")
    assert query.count(".drop()") == 1
    assert f"has('user_name', {backend._gremlin_literal('tenant-1')})" in query
    backend._g.getVerticesById.assert_called_once_with([hostile_id])


def test_update_filter_fields_refreshes_vector_payload_without_new_embedding():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(
        return_value={
            "id": MEMORY_ID,
            "memory_type": "LongTermMemory",
            "status": "activated",
            "mem_cube_id": "cube-1",
            "embedding_json": "[0.1, 0.2]",
            "metadata_json": "{}",
        }
    )

    backend.update_node(MEMORY_ID, {"status": "archived"})

    vector_item = backend._vector_index.upsert.call_args.args[0][0]
    assert vector_item.vector == [0.1, 0.2]
    assert vector_item.payload["status"] == "archived"


def test_delete_node_surfaces_vector_failure_before_graph_delete():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(return_value={"id": MEMORY_ID})
    backend._vector_index.delete.side_effect = RuntimeError("vector unavailable")

    with pytest.raises(RuntimeError, match="vector unavailable"):
        backend.delete_node(MEMORY_ID)

    backend._g.removeVertexById.assert_not_called()


def test_clear_deletes_tenant_vectors_before_graph_vertices():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [[MEMORY_ID], []]

    backend.clear()

    backend._vector_index.delete.assert_called_once_with([MEMORY_ID])
    queries = [call.args[0] for call in backend._gremlin.exec.call_args_list]
    assert queries[0].endswith(".values('id')")
    assert queries[1].endswith(".drop()")


def test_remove_oldest_memory_deletes_matching_vectors():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [[MEMORY_ID], []]

    backend.remove_oldest_memory("WorkingMemory", keep_latest=10)

    backend._vector_index.delete.assert_called_once_with([MEMORY_ID])
    queries = [call.args[0] for call in backend._gremlin.exec.call_args_list]
    assert ".range(10, -1).values('id')" in queries[0]
    assert ".range(10, -1).drop()" in queries[1]


def test_delete_by_mem_cube_id_deletes_matching_vectors():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [[MEMORY_ID], []]

    backend.delete_node_by_mem_cube_id(
        mem_cube_id="tenant-1", delete_record_id="record-1", hard_delete=True
    )

    backend._vector_index.delete.assert_called_once_with([MEMORY_ID])


def test_recover_by_mem_cube_id_refreshes_vector_status():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [
        [
            {
                "id": [MEMORY_ID],
                "memory_type": ["LongTermMemory"],
                "status": ["archived"],
                "mem_cube_id": ["cube-1"],
                "embedding_json": ["[0.1, 0.2]"],
            }
        ],
        [],
        [],
    ]

    backend.recover_memory_by_mem_cube_id("tenant-1", "record-1")

    vector_item = backend._vector_index.upsert.call_args.args[0][0]
    assert vector_item.vector == [0.1, 0.2]
    assert vector_item.payload["status"] == "activated"


def test_get_by_metadata_filters_json_metadata_with_and_semantics():
    backend = _backend_with_vector_index()
    second_id = "22222222-2222-4222-8222-222222222222"
    backend._gremlin.exec.return_value = [
        {
            "id": MEMORY_ID,
            "memory_type": ["LongTermMemory"],
            "metadata_json": ['{"key":"alpha","tags":["one","two"]}'],
        },
        {
            "id": second_id,
            "memory_type": ["LongTermMemory"],
            "metadata_json": ['{"key":"beta","tags":["three"]}'],
        },
    ]

    ids = backend.get_by_metadata(
        [
            {"field": "key", "op": "in", "value": ["alpha"]},
            {"field": "tags", "op": "contains", "value": ["two", "missing"]},
            {"field": "memory_type", "op": "=", "value": "LongTermMemory"},
        ]
    )

    assert ids == [MEMORY_ID]
    assert backend._gremlin.exec.call_args.args[0].endswith(".valueMap(true)")


def test_get_by_metadata_rejects_unknown_operator():
    backend = _backend_with_vector_index()

    with pytest.raises(ValueError, match="Unsupported metadata operator"):
        backend.get_by_metadata([{"field": "key", "op": "exec", "value": "x"}])


def test_embedding_search_hydrates_fields_with_requested_tenant():
    backend = _backend_with_vector_index()
    backend._vector_index.search.return_value = [SimpleNamespace(id=MEMORY_ID, score=0.9)]
    backend.get_nodes = MagicMock(
        return_value=[{"id": MEMORY_ID, "memory": "mine", "metadata": {}}]
    )

    backend.search_by_embedding([0.1, 0.2], return_fields=["memory"], user_name="tenant-2")

    backend.get_nodes.assert_called_once_with(
        [MEMORY_ID], include_embedding=False, user_name="tenant-2"
    )


def test_get_nodes_honors_include_embedding():
    backend = _backend_with_vector_index()
    backend._g.getVerticesById.return_value = [
        SimpleNamespace(
            properties={
                "id": MEMORY_ID,
                "memory": "mine",
                "user_name": "tenant-1",
                "embedding_json": "[0.1, 0.2]",
            }
        )
    ]

    nodes = backend.get_nodes([MEMORY_ID], include_embedding=True)

    assert nodes[0]["metadata"]["embedding"] == [0.1, 0.2]


def test_soft_delete_and_recover_support_server_router_signature():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [
        [
            {
                "id": MEMORY_ID,
                "status": ["activated"],
                "memory_type": ["LongTermMemory"],
                "mem_cube_id": ["cube-1"],
                "embedding_json": ["[0.1, 0.2]"],
            }
        ],
        [],
        [
            {
                "id": MEMORY_ID,
                "status": ["deleted"],
                "memory_type": ["LongTermMemory"],
                "mem_cube_id": ["cube-1"],
                "embedding_json": ["[0.1, 0.2]"],
            }
        ],
        [],
        [],
    ]

    deleted = backend.delete_node_by_mem_cube_id(
        mem_cube_id="tenant-1", delete_record_id="record-1", hard_delete=False
    )
    recovered = backend.recover_memory_by_mem_cube_id(
        mem_cube_id="tenant-1", delete_record_id="record-1"
    )

    assert deleted == 1
    assert recovered == 1
    vector_items = [call.args[0][0] for call in backend._vector_index.upsert.call_args_list]
    assert [item.payload["status"] for item in vector_items] == ["deleted", "activated"]


def test_delete_node_by_prams_supports_memory_ids_contract():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [
        [{"id": MEMORY_ID, "user_name": ["tenant-1"], "metadata_json": ["{}"]}],
        [],
    ]

    count = backend.delete_node_by_prams(memory_ids=[MEMORY_ID])

    assert count == 1
    backend._vector_index.delete.assert_called_once_with([MEMORY_ID])


def test_add_node_retry_repairs_vector_after_graph_partial_write():
    backend = _backend_with_vector_index()
    backend._get_vertex_by_node_id = MagicMock(return_value={"id": MEMORY_ID})

    backend.add_node(
        MEMORY_ID,
        "remember this",
        {"embedding": [0.1, 0.2], "status": "activated"},
    )

    backend._g.addVertex.assert_not_called()
    backend._g.appendVertex.assert_called_once()
    backend._vector_index.upsert.assert_called_once()


def test_delete_node_by_prams_supports_cube_file_and_nested_filter_contract():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.side_effect = [
        [
            {
                "id": MEMORY_ID,
                "user_name": ["cube-a"],
                "metadata_json": ['{"file_ids":["file-1"],"user_id":"user-1","tags":["keep"]}'],
            }
        ],
        [],
    ]

    count = backend.delete_node_by_prams(
        writable_cube_ids=["cube-a"],
        file_ids=["file-1"],
        filter={"and": [{"user_id": "user-1"}, {"tags": {"contains": "keep"}}]},
    )

    assert count == 1
    first_query = backend._gremlin.exec.call_args_list[0].args[0]
    assert 'within(*["cube-a"])' in first_query


def test_path_traversal_scopes_vertices_and_edges_to_tenant():
    backend = _backend_with_vector_index()
    target_id = "22222222-2222-4222-8222-222222222222"

    backend.get_path(MEMORY_ID, target_id, user_name="tenant-1")

    query = backend._gremlin.exec.call_args.args[0]
    assert query.count("has('user_name', \"tenant-1\")") >= 3


def test_delete_node_by_prams_postfilters_rows_outside_tenant():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.return_value = [
        {"id": MEMORY_ID, "user_name": ["tenant-2"], "metadata_json": ["{}"]}
    ]

    assert backend.delete_node_by_prams(memory_ids=[MEMORY_ID]) == 0
    backend._vector_index.delete.assert_not_called()


def test_delete_node_by_prams_rejects_unknown_filter_operator():
    backend = _backend_with_vector_index()
    backend._gremlin.exec.return_value = [
        {
            "id": MEMORY_ID,
            "user_name": ["tenant-1"],
            "metadata_json": ['{"key":"alpha"}'],
        }
    ]

    with pytest.raises(ValueError, match="Unsupported delete filter operator"):
        backend.delete_node_by_prams(filter={"key": {"exec": "drop"}})

    backend._vector_index.delete.assert_not_called()


def test_recovery_vector_failure_is_retryable_before_graph_activation():
    backend = _backend_with_vector_index()
    row = {
        "id": MEMORY_ID,
        "status": ["deleted"],
        "memory_type": ["LongTermMemory"],
        "mem_cube_id": ["cube-1"],
        "embedding_json": ["[0.1, 0.2]"],
    }
    backend._gremlin.exec.return_value = [row]
    backend._vector_index.upsert.side_effect = RuntimeError("vector unavailable")

    with pytest.raises(RuntimeError, match="vector unavailable"):
        backend.recover_memory_by_mem_cube_id("tenant-1", "record-1")

    assert backend._gremlin.exec.call_count == 1
    backend._vector_index.upsert.side_effect = None
    backend._gremlin.exec.reset_mock()
    backend._gremlin.exec.side_effect = [[row], []]

    assert backend.recover_memory_by_mem_cube_id("tenant-1", "record-1") == 1
